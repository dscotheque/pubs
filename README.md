# DScotheque Lab Publications

Publication tracking for DSCO. Powered by [labpubs](https://github.com/nniiicc/labpubs).

Syncs publications from **OpenAlex**, **Semantic Scholar**, and **Crossref** into a local SQLite database with deduplication, exports, and Slack notifications. MCP coming soon. 

## Setup

```bash
# Install dependencies
uv sync

# Run initial sync (takes ~15-30 minutes for all researchers)
uv run labpubs -c labpubs.yaml sync

# Verify publications were imported
uv run labpubs -c labpubs.yaml list
```

## REST API

A FastAPI server exposes the publication database over HTTP.

```bash
# Start the API server
uv run uvicorn pubs_api.app:app --host 0.0.0.0 --port 8000
```

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/researchers` | List all tracked lab members |
| GET | `/works` | List publications (query params: `researcher`, `year`, `funder`, `limit`) |
| GET | `/works/search?q=` | Full-text search across titles and abstracts |
| GET | `/works/{doi}` | Get a specific publication by DOI |
| GET | `/export/bibtex` | Export as BibTeX (query params: `researcher`, `year`) |
| GET | `/export/json` | Export as JSON |
| GET | `/export/csl-json` | Export as CSL-JSON (for citation managers) |
| GET | `/stats` | Summary statistics |

Interactive docs available at `http://localhost:8000/docs` when the server is running.

### Example

```bash
# Get all publications
curl http://localhost:8000/works

# Search for a topic
curl "http://localhost:8000/works/search?q=misinformation"

# Get a researcher's publications
curl "http://localhost:8000/works?researcher=Jevin+West"

# Export BibTeX for a specific year
curl "http://localhost:8000/export/bibtex?year=2024"
```

## MCP Server

labpubs includes a built-in MCP server with 17 tools for AI assistant integration.

```bash
# Start the MCP server
uv run labpubs -c labpubs.yaml mcp
```

### Claude Desktop Configuration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "labpubs": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/pubs", "labpubs", "-c", "labpubs.yaml", "mcp"]
    }
  }
}
```

## Nightly Sync (GitHub Actions)

A GitHub Action runs daily at 6:00 AM UTC to sync new publications and notify Slack.

The workflow:
1. Fetches new publications from OpenAlex, Semantic Scholar, and Crossref
2. Posts new finds to the `#lab-papers` Slack channel
3. Commits the updated database back to the repo

### Required GitHub Secret

Add `SLACK_WEBHOOK_URL` at **Settings > Secrets and variables > Actions**.

## Slack Integration

To set up the Slack notification channel:

1. Go to [api.slack.com/apps](https://api.slack.com/apps) and click **Create New App** > **From scratch**
2. Name it (e.g., "Lab Publications Bot"), select your workspace
3. In the left sidebar, click **Incoming Webhooks** > toggle **On**
4. Click **Add New Webhook to Workspace**
5. Select the `#lab-papers` channel (or create it first) and click **Allow**
6. Copy the Webhook URL

Store it as:
- **GitHub Secret**: `SLACK_WEBHOOK_URL` (for the nightly cron)
- **Local `.env` file** (for manual testing):
  ```
  SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T.../B.../...
  ```

### Test notifications locally

```bash
export SLACK_WEBHOOK_URL=$(grep SLACK_WEBHOOK_URL .env | cut -d= -f2)
sed "s|\${SLACK_WEBHOOK_URL}|$SLACK_WEBHOOK_URL|g" labpubs.yaml > /tmp/labpubs-resolved.yaml
uv run labpubs -c /tmp/labpubs-resolved.yaml notify --days 7
```

## CLI Reference

```bash
# Sync all researchers
uv run labpubs -c labpubs.yaml sync

# Sync one researcher
uv run labpubs -c labpubs.yaml sync --researcher "Jevin West"

# List publications
uv run labpubs -c labpubs.yaml list
uv run labpubs -c labpubs.yaml list --researcher "Nic Weber" --year 2024

# Export
uv run labpubs -c labpubs.yaml export bibtex -o pubs.bib
uv run labpubs -c labpubs.yaml export json -o pubs.json

# Show details for a specific work
uv run labpubs -c labpubs.yaml show "some search query"

# List researchers and their IDs
uv run labpubs -c labpubs.yaml researchers
```

## Development

```bash
# Install with dev dependencies
uv sync --extra dev

# Run tests
uv run pytest

# Lint
uv run ruff check src/ tests/

# Format
uv run ruff format src/ tests/
```

## Adding a New Lab Member

Edit `labpubs.yaml` and add an entry under `researchers:`:

```yaml
- name: "New Person"
  orcid: "0000-0000-0000-0000"
  openalex_id: "A5000000000"  # Look up at https://api.openalex.org/authors/https://orcid.org/ORCID
```

Then run `uv run labpubs -c labpubs.yaml sync --researcher "New Person"`.
