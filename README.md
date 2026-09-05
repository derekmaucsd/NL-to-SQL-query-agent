# Natural Language (NL) to SQL database querying agent

## Data

This agent was built and tested against an NBA dataset, which is a naturally good example with both understandability and potential question depth.

The NBA dataset is not stored in this GitHub repo because the SQLite database
and CSV exports are large. Download the data locally from Kaggle:

https://www.kaggle.com/datasets/wyattowalsh/basketball?resource=download

After downloading, place the files in the repo root like this:

```text
nba-query-agent/
  nba.sqlite
  csv/
    common_player_info.csv
    game.csv
    play_by_play.csv
    ...
```

The local data files are ignored by Git via `.gitignore`.

## SQLite EDA

Run a quick schema and sample-data report with:

```powershell
python scripts\eda_sqlite.py --db nba.sqlite --out reports\sqlite_eda.md
```

## Gemini Setup

Create a local `.env` file in the repo root and add your API key:

```text
GEMINI_API_KEY=your_key_here
```

Then run the agent:

```powershell
python nba_agent.py --question "How many games were there total in the NBA?"
```

The script will read `.env` automatically. Do not commit that file.

## Question Traces

Every `nba_agent.py` run creates a timestamped JSON file in `traces/`. The trace
records the user question, schema inspection, every Gemini prompt and response,
every generated SQL execution and its rows or error, timing information, and the
final result. The CLI prints the trace path when the run finishes, including when
the run fails.

Generated trace JSON files are ignored by Git because they can be large and may
contain user questions or model inputs that should remain local.
