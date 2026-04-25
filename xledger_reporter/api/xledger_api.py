"""
Xledger GraphQL API client.

Authentication: Administration > System Access > API Access Tokens
Endpoint:       https://www.xledger.net/graphql  (or your company subdomain)
Header:         Authorization: token <TOKEN>
"""
import httpx
from typing import Any

# Keywords used to identify time/hours-related query types in the schema
_TIME_KEYWORDS = [
    "time", "hour", "sheet", "registr", "work", "payroll",
    "tid",   # Norwegian: time
    "timer", # Norwegian: hours
    "prosjekt",  # Norwegian: project
]

# Ordered list of query names to try for timesheet data
_TIMESHEET_CANDIDATES = [
    "timesheets",
    "timeRegistrations",
    "timeRegistration",
    "timeEntries",
    "timeEntry",
    "workHours",
    "projectHours",
    "timesheetEntries",
    "timesheetLines",
    "payrollTimesheets",
]


class XledgerClient:
    def __init__(self, token: str, url: str = "https://www.xledger.net/graphql"):
        self.url = url
        self.headers = {
            "Authorization": f"token {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _post(self, gql: str, variables: dict | None = None) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                self.url,
                json={"query": gql, "variables": variables or {}},
                headers=self.headers,
            )
            resp.raise_for_status()
            body = resp.json()
            if "errors" in body:
                msgs = "; ".join(e.get("message", "Unknown") for e in body["errors"])
                raise ValueError(f"GraphQL error: {msgs}")
            return body.get("data", {})

    async def ping(self) -> str:
        """Minimal query — confirms the token works."""
        data = await self._post("{ __typename }")
        return data.get("__typename", "ok")

    async def discover_time_queries(self) -> list[dict]:
        """
        Introspect the schema and return all root query fields whose name
        contains a time/hours keyword.
        """
        data = await self._post("""
        {
          __schema {
            queryType {
              fields {
                name
                description
                args { name type { name kind } }
              }
            }
          }
        }
        """)
        all_fields = data.get("__schema", {}).get("queryType", {}).get("fields", [])
        return [
            f for f in all_fields
            if any(kw in f["name"].lower() for kw in _TIME_KEYWORDS)
        ]

    async def probe_timesheet_query(self) -> str | None:
        """
        Try each candidate query name until one works.
        Returns the working query name, or None if none found.
        """
        for name in _TIMESHEET_CANDIDATES:
            try:
                # Minimal introspection — does this field exist?
                data = await self._post(f"""
                {{
                  __type(name: "Query") {{
                    fields(includeDeprecated: true) {{
                      name
                    }}
                  }}
                }}
                """)
                # Parse list from introspection
                fields = data.get("__type", {}).get("fields", [])
                names = {f["name"] for f in fields}
                if name in names:
                    return name
            except Exception:
                pass
        return None

    async def fetch_timesheets(
        self,
        query_name: str,
        from_date: str | None = None,
        to_date: str | None = None,
        after: str | None = None,
        page_size: int = 1000,
    ) -> dict:
        """
        Fetch one page of timesheet data using the discovered query name.
        Returns the raw connection object {edges: [{node: {...}}], pageInfo: {...}}.
        """
        # Build filter args if dates provided
        filter_args = ""
        if from_date or to_date:
            parts = []
            if from_date:
                parts.append(f'assignmentDate_gte: "{from_date}"')
            if to_date:
                parts.append(f'assignmentDate_lte: "{to_date}"')
            filter_args = ", ".join(parts)

        after_arg = f', after: "{after}"' if after else ""
        filter_clause = f", {filter_args}" if filter_args else ""

        gql = f"""
        {{
          {query_name}(first: {page_size}{after_arg}{filter_clause}) {{
            edges {{
              cursor
              node {{
                dbId
                assignmentDate
                workingHours
                description
              }}
            }}
            pageInfo {{
              hasNextPage
              endCursor
            }}
          }}
        }}
        """
        data = await self._post(gql)
        return data.get(query_name, {})

    async def fetch_all_timesheets(
        self,
        query_name: str,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> list[dict]:
        """Fetch all pages and return flat list of nodes."""
        rows: list[dict] = []
        after = None
        while True:
            page = await self.fetch_timesheets(query_name, from_date, to_date, after)
            edges = page.get("edges", [])
            rows.extend(e["node"] for e in edges if "node" in e)
            page_info = page.get("pageInfo", {})
            if not page_info.get("hasNextPage"):
                break
            after = page_info.get("endCursor")
        return rows


def build_html_table(rows: list[dict]) -> str:
    if not rows:
        return "<p>No timesheet data found for the selected period.</p>"
    headers = list(rows[0].keys())
    header_row = "".join(f"<th>{h}</th>" for h in headers)
    data_rows = "".join(
        "<tr>" + "".join(f"<td>{r.get(h, '')}</td>" for h in headers) + "</tr>"
        for r in rows
    )
    return f"""
<table border="1" cellpadding="6" cellspacing="0"
       style="border-collapse:collapse;font-family:Arial,sans-serif;font-size:13px">
  <thead style="background:#f0f0f5"><tr>{header_row}</tr></thead>
  <tbody>{data_rows}</tbody>
</table>"""
