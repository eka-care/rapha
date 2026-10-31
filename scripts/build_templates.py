"""Generate the operation atom and the questionnaire for every declared template.

Run: python3 scripts/build_templates.py [bundle_id]

This is the first compile step, before catalogue/build.py, because what it
writes are ordinary operation atoms and ordinary questionnaires that the
existing lint then has to pass. That is the point: a template gets no weaker
check than a hand written operation, it gets the same one.

What it writes is derived entirely from the `templates` declaration in
bundles/<id>/bundle.yaml and the base operation it names. kernel/templates.py
holds the narrowing and the lint; this script only reads the manifest, asks
for the files and writes the ones that changed.

Nothing here invents clinical content, and nothing here may: the generator
copies questions, bindings and mapping sources from the base atom and drops
the ones a template does not ask for.
"""
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from kernel import templates                                  # noqa: E402


def main(bundle_id="phc"):
    manifest = yaml.safe_load(
        (ROOT / "bundles" / bundle_id / "bundle.yaml").read_text())
    wanted = templates.generate(manifest)
    if not wanted:
        print("ok   bundle %s declares no template" % bundle_id)
        return 0
    changed = []
    for path, text in sorted(wanted.items()):
        if not path.exists() or path.read_text() != text:
            path.write_text(text)
            changed.append(path.name)
    print("ok   %d templates generated %d files%s"
          % (len(templates.declared(manifest)), len(wanted),
             (", wrote " + ", ".join(sorted(changed))) if changed else ", all current"))
    return 0


if __name__ == "__main__":
    sys.exit(main(*(a for a in sys.argv[1:] if not a.startswith("-"))))
