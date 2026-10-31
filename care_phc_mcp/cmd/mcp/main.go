// care_phc_mcp serves the PHC operation catalogue to an agent over MCP.
//
// It talks to CARE over HTTP as a service account, using the same REST API the
// rendered surface uses. That is deliberate. If this reached the guard in
// process it could also reach past CARE's own API layer, and "invoked
// identically from both surfaces" would be a claim rather than a fact. Over the
// wire, bypassing is not expressible.
//
// Reads execute. Writes propose, and there is no tool that commits.
//
// The catalogue reader is carephc, shared with cmd/api, so there is one parser
// of catalogue.json in this module and not one per command.
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"strings"
	"time"

	carephc "github.com/eka-care/care_phc_mcp"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

type Client struct {
	Base  string
	Token string
	HTTP  *http.Client
}

func (c *Client) do(ctx context.Context, method, path string, body any) ([]byte, error) {
	var payload io.Reader
	if body != nil {
		b, err := json.Marshal(body)
		if err != nil {
			return nil, err
		}
		payload = bytes.NewReader(b)
	}
	req, err := http.NewRequestWithContext(ctx, method, strings.TrimRight(c.Base, "/")+path, payload)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Authorization", "Bearer "+c.Token)
	req.Header.Set("Content-Type", "application/json")
	resp, err := c.HTTP.Do(req)
	if err != nil {
		return nil, fmt.Errorf("CARE unreachable at %s: %w", c.Base, err)
	}
	defer resp.Body.Close()
	out, _ := io.ReadAll(resp.Body)
	if resp.StatusCode >= 400 {
		return nil, fmt.Errorf("CARE returned %s: %s", resp.Status, strings.TrimSpace(string(out)))
	}
	return out, nil
}

// capabilities asks CARE what this service account may do. The tool list is
// built from the answer, so an account never sees a tool it cannot use.
func (c *Client) capabilities(ctx context.Context) (map[string]bool, error) {
	if env := os.Getenv("PHC_CAPABILITIES"); env != "" {
		// Offline escape hatch for inspecting the tool list without a CARE.
		caps := map[string]bool{}
		for _, s := range strings.Split(env, ",") {
			caps[strings.TrimSpace(s)] = true
		}
		return caps, nil
	}
	body, err := c.do(ctx, http.MethodGet, "/api/v1/phc/whoami/", nil)
	if err != nil {
		return nil, err
	}
	var out struct {
		Capabilities []string `json:"capabilities"`
	}
	if err := json.Unmarshal(body, &out); err != nil {
		return nil, err
	}
	caps := map[string]bool{}
	for _, cap := range out.Capabilities {
		caps[cap] = true
	}
	return caps, nil
}

// loaded asks the kernel which operations the bundle it started with actually
// holds. catalogue.json is embedded at build time and carries every bundle's
// atoms, so without this a server pointed at a laboratory kernel offers
// propose_vitals_record, which that kernel answers with a 404. An empty result
// means "do not narrow": the offline escape hatch below never asks.
func (c *Client) loaded(ctx context.Context) (map[string]bool, error) {
	body, err := c.do(ctx, http.MethodGet, "/api/v1/phc/facility/", nil)
	if err != nil {
		return nil, err
	}
	var out struct {
		Bundle struct {
			Operations []string `json:"operations"`
		} `json:"bundle"`
	}
	if err := json.Unmarshal(body, &out); err != nil {
		return nil, err
	}
	ids := map[string]bool{}
	for _, id := range out.Bundle.Operations {
		ids[id] = true
	}
	return ids, nil
}

func text(s string) *mcp.CallToolResult {
	return &mcp.CallToolResult{Content: []mcp.Content{&mcp.TextContent{Text: s}}}
}

func fail(format string, a ...any) *mcp.CallToolResult {
	return &mcp.CallToolResult{
		IsError: true,
		Content: []mcp.Content{&mcp.TextContent{Text: fmt.Sprintf(format, a...)}},
	}
}

func handler(c *Client, op carephc.Operation) mcp.ToolHandler {
	return func(ctx context.Context, req *mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		var args map[string]any
		if len(req.Params.Arguments) > 0 {
			if err := json.Unmarshal(req.Params.Arguments, &args); err != nil {
				return fail("arguments are not valid JSON: %v", err), nil
			}
		}
		patient, _ := args["patient"].(string)
		delete(args, "patient")

		path := "/api/v1/phc/operations/" + op.ID + "/"
		if op.Kind == "write" {
			path += "propose/"
		}
		body, err := c.do(ctx, http.MethodPost, path,
			map[string]any{"patient": patient, "payload": args})
		if err != nil {
			// The guard's denials arrive here as 4xx with their reason, which
			// is the useful thing to hand back to an agent.
			return fail("%v", err), nil
		}
		if op.Kind == "write" {
			return text(fmt.Sprintf(
				"Proposed, not committed. %s\n\nA clinician must review and "+
					"confirm this on screen before anything is written.",
				strings.TrimSpace(string(body)))), nil
		}
		return text(strings.TrimSpace(string(body))), nil
	}
}

// khojHandler forwards an agent's search or question straight to the kernel's
// own Khoj route, whatever shape the caller sent: `utterance`, and `patient`
// if the question is about one thread. api/main.py's thread_of() already
// treats `patient` as an alias for `thread`, which is why nothing here needs
// to translate the argument names first.
//
// There is no write branch: khoj.Endpoint is the propose-only route, so this
// can only ever return what that route returns, and that route has no path
// to confirm or commit.
func khojHandler(c *Client, khoj carephc.Khoj) mcp.ToolHandler {
	return func(ctx context.Context, req *mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		var args map[string]any
		if len(req.Params.Arguments) > 0 {
			if err := json.Unmarshal(req.Params.Arguments, &args); err != nil {
				return fail("arguments are not valid JSON: %v", err), nil
			}
		}
		body, err := c.do(ctx, http.MethodPost, khoj.Endpoint, args)
		if err != nil {
			return fail("%v", err), nil
		}
		return text(strings.TrimSpace(string(body))), nil
	}
}

func main() {
	base := os.Getenv("CARE_BASE_URL")
	token := os.Getenv("CARE_SERVICE_TOKEN")
	if base == "" {
		log.Fatal("set CARE_BASE_URL to your CARE instance, " +
			"and CARE_SERVICE_TOKEN to a service account token")
	}
	client := &Client{Base: base, Token: token, HTTP: &http.Client{Timeout: 30 * time.Second}}

	cat, err := carephc.Load()
	if err != nil {
		log.Fatal(err)
	}
	ctx := context.Background()
	caps, err := client.capabilities(ctx)
	if err != nil {
		log.Fatalf("could not read this account's capabilities: %v", err)
	}
	// Only when we are actually talking to a kernel. With PHC_CAPABILITIES set
	// there is nothing to ask, and the embedded catalogue is the whole answer.
	var bundle map[string]bool
	if os.Getenv("PHC_CAPABILITIES") == "" {
		if bundle, err = client.loaded(ctx); err != nil {
			// Not fatal. Narrowing keeps a lab tool off a health centre's list;
			// it is not what stops a write, the kernel is, and it answers an
			// operation it never loaded with a 404 either way. Something that
			// serves /whoami but not /facility (scripts/mock_care.py) should
			// still start, loudly.
			log.Printf("care-phc: cannot tell which bundle this kernel loaded "+
				"(%v); offering every embedded operation this account may use", err)
			bundle = nil
		}
	}

	server := mcp.NewServer(&mcp.Implementation{
		Name: "care-phc", Version: "0.1.0",
	}, nil)
	ops := cat.For(caps, bundle)
	for _, op := range ops {
		schema, err := json.Marshal(op.InputSchema())
		if err != nil {
			log.Fatalf("%s: %v", op.ID, err)
		}
		server.AddTool(&mcp.Tool{
			Name:        op.Tool,
			Title:       op.Title,
			Description: op.ToolDescription(),
			InputSchema: json.RawMessage(schema),
		}, handler(client, op))
	}

	// Khoj is not one operation gated by one capability; every account that
	// can reach this server may search and ask, and the guard still runs
	// underneath whatever it proposes. Its name and description come from
	// the compiled catalogue's own manifest, not from a string typed here.
	if cat.Manifest.Khoj.Tool != "" {
		server.AddTool(&mcp.Tool{
			Name:        cat.Manifest.Khoj.Tool,
			Title:       "Khoj",
			Description: cat.Manifest.Khoj.Description,
			InputSchema: json.RawMessage(`{"type":"object","properties":{` +
				`"utterance":{"type":"string","description":"What to search for, or ask."},` +
				`"patient":{"type":"string","description":"The patient thread this question is about, if any."}` +
				`},"required":["utterance"]}`),
		}, khojHandler(client, cat.Manifest.Khoj))
	}
	log.Printf("care-phc: %d of %d operations available to this account, plus khoj",
		len(ops), len(cat.Operations))

	if err := server.Run(ctx, &mcp.StdioTransport{}); err != nil {
		log.Fatal(err)
	}
}
