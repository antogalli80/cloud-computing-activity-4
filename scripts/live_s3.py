"""Real HTTP integration evidence. Never print or persist session credentials."""

import asyncio
import base64
import hashlib
import json
import os
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import httpx
from pypdf import PdfReader, PdfWriter


async def main():
    auth_url = os.getenv("AUTH_BASE_URL", "http://localhost:8101")
    files_url = os.getenv("FILES_BASE_URL", "http://localhost:8102")
    results = []
    async with httpx.AsyncClient(timeout=30) as client:

        def check(label, condition):
            assert condition, label
            results.append({"check": label, "result": "PASS"})

        email = f"live-{uuid4().hex}@example.com"
        credentials = {"email": email, "password": "synthetic-test-password-only"}
        response = await client.post(auth_url + "/authentication/register", json=credentials)
        check(
            "Registration and integer identity",
            response.status_code == 200 and isinstance(response.json()["user"]["external_id"], int),
        )
        responses = await asyncio.gather(
            *(client.post(auth_url + "/authentication/login", json=credentials) for _ in range(6))
        )
        check(
            "Concurrent login: one success, five conflicts",
            sorted(r.status_code for r in responses) == [200, 409, 409, 409, 409, 409],
        )
        token = next(r.json()["token"] for r in responses if r.status_code == 200)
        request_id = str(uuid4())
        headers = {"Auth": token, "X-Request-ID": request_id}
        ids = []
        for width in [100, 200, 300]:
            response = await client.post(
                files_url + "/files", json={"filename": f"{width}.pdf"}, headers=headers
            )
            check(
                f"Metadata creation {width}",
                response.status_code == 200 and not response.json()["file"]["has_content"],
            )
            file_id = response.json()["file"]["id"]
            ids.append(file_id)
            writer = PdfWriter()
            writer.add_blank_page(width=width, height=100)
            stream = BytesIO()
            writer.write(stream)
            response = await client.post(
                files_url + f"/files/{file_id}",
                files={"file_content": ("a.pdf", stream.getvalue(), "application/pdf")},
                headers=headers,
            )
            check(f"Content upload {width}", response.status_code == 200)
        response = await client.post(
            files_url + "/files/merge", json={"file_ids": ids}, headers=headers
        )
        check("Three-file merge over real HTTP introspection", response.status_code == 200)
        merged = response.json()["file"]["id"]
        response = await client.get(files_url + f"/files/{merged}", headers=headers)
        data = base64.b64decode(response.json()["content_base64"])
        check(
            "Merged page order and integrity",
            [int(p.mediabox.width) for p in PdfReader(BytesIO(data)).pages] == [100, 200, 300]
            and hashlib.sha256(data).hexdigest() == response.json()["sha256"],
        )
        other = {
            "email": f"other-{uuid4().hex}@example.com",
            "password": "synthetic-other-password",
        }
        await client.post(auth_url + "/authentication/register", json=other)
        other_token = (await client.post(auth_url + "/authentication/login", json=other)).json()[
            "token"
        ]
        denied = await client.get(files_url + f"/files/{merged}", headers={"Auth": other_token})
        missing = await client.get(files_url + "/files/99999999", headers={"Auth": other_token})
        check(
            "Owner isolation without existence disclosure",
            denied.status_code == 404 and denied.json() == missing.json(),
        )
        check("Request correlation", response.headers.get("X-Request-ID") == request_id)
        check(
            "File deletion",
            (await client.delete(files_url + f"/files/{merged}", headers=headers)).status_code
            == 200,
        )
        check(
            "Logout",
            (await client.post(auth_url + "/authentication/logout", headers=headers)).status_code
            == 200,
        )
        check(
            "Revoked token blocked in Files",
            (await client.get(files_url + "/files", headers=headers)).status_code == 401,
        )
        await client.post(auth_url + "/authentication/logout", headers={"Auth": other_token})
    output = {
        "checks": results,
        "passed": len(results),
        "request_id": request_id,
        "transport": "real HTTP between separate services",
    }
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/live-http.json").write_text(json.dumps(output, indent=2))
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
