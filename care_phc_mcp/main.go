// care_phc_mcp serves the PHC operation catalogue to an agent over MCP.
//
// It talks to CARE over HTTP as a service account, using the same REST API the
// rendered surface uses. That is deliberate. If this reached the guard in
// process it could also reach past CARE's own API layer, and "invoked
// identically from both surfaces" would be a claim rather than a fact. Over the
// wire, bypassing is not expressible.
//
// Reads execute. Writes propose, and there is no tool that commits.
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

func text(s string) *mcp.CallToolResult {
	return &mcp.CallToolResult{Content: []mcp.Content{&mcp.TextContent{Text: s}}}
}

func fail(format string, a ...any) *mcp.CallToolResult {
	return &mcp.CallToolResult{
		IsError: true,
		Content: []mcp.Content{&mcp.TextContent{Text: fmt.Sprintf(format, a...)}},
	}
}

func handler(c *Client, op Operation) mcp.ToolHandler {
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

func main() {
	base := os.Getenv("CARE_BASE_URL")
	token := os.Getenv("CARE_SERVICE_TOKEN")
	if base == "" {
		log.Fatal("set CARE_BASE_URL to your CARE instance, " +
			"and CARE_SERVICE_TOKEN to a service account token")
	}
	client := &Client{Base: base, Token: token, HTTP: &http.Client{Timeout: 30 * time.Second}}

	cat, err := Load()
	if err != nil {
		log.Fatal(err)
	}
	ctx := context.Background()
	caps, err := client.capabilities(ctx)
	if err != nil {
		log.Fatalf("could not read this account's capabilities: %v", err)
	}

	server := mcp.NewServer(&mcp.Implementation{
		Name: "care-phc", Version: "0.1.0",
	}, nil)
	ops := cat.For(caps)
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
	log.Printf("care-phc: %d of %d operations available to this account",
		len(ops), len(cat.Operations))

	if err := server.Run(ctx, &mcp.StdioTransport{}); err != nil {
		log.Fatal(err)
	}
}
