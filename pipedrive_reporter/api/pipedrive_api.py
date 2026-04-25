"""
Pipedrive REST API client.

Authentication: Settings > Personal preferences > API
Header: x-api-token: <TOKEN>
"""
import httpx


class PipedriveClient:
    def __init__(self, token: str, company_domain: str = "akselera"):
        self.base_v1 = f"https://{company_domain}.pipedrive.com/api/v1"
        self.base_v2 = f"https://{company_domain}.pipedrive.com/api/v2"
        self.headers = {
            "x-api-token": token,
            "Accept": "application/json",
        }

    async def _get(self, url: str, params: dict | None = None) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, params=params or {}, headers=self.headers)
            resp.raise_for_status()
            body = resp.json()
            if not body.get("success"):
                raise ValueError(body.get("error") or body.get("message") or "API error")
            return body

    async def ping(self) -> dict:
        body = await self._get(f"{self.base_v1}/users/me")
        return body.get("data", {})

    async def raw_deals_sample(self) -> dict:
        """Return raw first-page response from both v1 and v2 for debugging."""
        results = {}
        for label, url in (("v1", f"{self.base_v1}/deals"), ("v2", f"{self.base_v2}/deals")):
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(
                        url, params={"limit": 3, "status": "open"}, headers=self.headers
                    )
                    body = resp.json()
                    results[label] = {
                        "status_code": resp.status_code,
                        "success": body.get("success"),
                        "data_type": type(body.get("data")).__name__,
                        "data_len": len(body.get("data") or []) if isinstance(body.get("data"), list) else "n/a",
                        "top_keys": list((body.get("data") or [{}])[0].keys())[:10]
                            if isinstance(body.get("data"), list) and body.get("data") else [],
                        "additional_data": body.get("additional_data"),
                        "error": body.get("error"),
                    }
            except Exception as e:
                results[label] = {"error": str(e)}
        return results

    async def fetch_deals_page_v1(
        self,
        status: str = "open",
        start: int = 0,
        limit: int = 500,
    ) -> dict:
        return await self._get(f"{self.base_v1}/deals", {
            "status": status,
            "start": start,
            "limit": limit,
        })

    async def fetch_all_deals(
        self,
        status: str = "open",
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> list[dict]:
        rows: list[dict] = []
        start = 0
        while True:
            body = await self.fetch_deals_page_v1(status=status, start=start)
            data = body.get("data") or []
            if not data:
                break
            for deal in data:
                flat = _flatten_deal(deal)
                if from_date and flat["Updated"] and flat["Updated"] < from_date:
                    continue
                if to_date and flat["Updated"] and flat["Updated"] > to_date:
                    continue
                rows.append(flat)
            pagination = (body.get("additional_data") or {}).get("pagination", {})
            if not pagination.get("more_items_in_collection"):
                break
            start = pagination.get("next_start", start + 500)
        return rows


def _name_of(obj) -> str:
    if not obj:
        return ""
    if isinstance(obj, dict):
        return obj.get("name") or str(obj.get("value") or obj.get("id") or "")
    return str(obj)


def _flatten_deal(d: dict) -> dict:
    return {
        "ID":             d.get("id", ""),
        "Title":          d.get("title", ""),
        "Value":          d.get("value", ""),
        "Currency":       d.get("currency", ""),
        "Status":         d.get("status", ""),
        "Owner":          _name_of(d.get("owner_id")),
        "Organization":   _name_of(d.get("org_id")),
        "Contact":        _name_of(d.get("person_id")),
        "Expected Close": (d.get("expected_close_date") or "")[:10],
        "Added":          (d.get("add_time") or "")[:10],
        "Updated":        (d.get("update_time") or "")[:10],
    }


def build_html_table(rows: list[dict]) -> str:
    if not rows:
        return "<p>No deals found for the selected criteria.</p>"
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
