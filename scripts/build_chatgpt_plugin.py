"""Build a portable plugin ZIP after a real endpoint and publisher are known."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]


def https_url(value):
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise argparse.ArgumentTypeError("A real HTTPS URL without embedded credentials is required")
    if parsed.hostname in {"localhost", "example.com"} or parsed.hostname.endswith(".example.com"):
        raise argparse.ArgumentTypeError("Placeholder or localhost URLs cannot be submitted")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mcp-url", required=True, type=https_url)
    parser.add_argument("--developer-name", required=True)
    for name in ("website", "support", "privacy", "terms", "demo"):
        parser.add_argument("--" + name + "-url", required=True, type=https_url)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/budongsan-tax-chatgpt.zip")
    args = parser.parse_args()
    if not args.developer_name.strip() or len(args.developer_name) > 80:
        parser.error("Use the verified publisher display name (1-80 characters)")
    manifest = json.loads((ROOT / "plugin/manifest.template.json").read_text(encoding="utf-8"))
    manifest["author"] = {"name": args.developer_name}
    ext = manifest["extensions"]["com.openai"]
    ext["interface"].update({
        "developerName": args.developer_name, "websiteURL": args.website_url,
        "supportURL": args.support_url, "privacyPolicyURL": args.privacy_url,
        "termsOfServiceURL": args.terms_url,
    })
    ext["review"]["demo_recording_url"] = args.demo_url
    ext["review"]["test_cases"] = json.loads((ROOT / "plugin/review-cases.json").read_text(encoding="utf-8"))
    config = {"$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
              "mcpServers": {"budongsan-tax": {"type": "streamable-http", "url": args.mcp_url}}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(args.output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("plugin.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.writestr("mcp.json", json.dumps(config, indent=2))
        archive.write(ROOT / "plugin/assets/icon.svg", "assets/icon.svg")
    print(args.output)
    print("Package built; platform scan, identity/domain verification and review still required.")


if __name__ == "__main__":
    main()
