package views

import (
	"errors"
	"testing"
	"time"

	carephc "github.com/eka-care/care_phc_mcp"
)

// A calendar day is exactly YYYY-MM-DD; kernel/views._day refuses the rest.
func TestACalendarDayIsOnlyYYYYMMDD(t *testing.T) {
	for _, bad := range []string{"31st October", "2026-11-04T00:00:00", "20261104",
		"2026-W45-3", "2026-1-4", ""} {
		on := bad
		_, _, err := calendar(Bundle{}, carephc.View{}, nil, &on, time.Now())
		var declared Declared
		if !errors.As(err, &declared) {
			t.Errorf("%q was accepted as a day (err %v)", bad, err)
		}
	}
}
