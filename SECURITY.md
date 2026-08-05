# Security Policy

Traffic Crash Notebook may hold sensitive investigative working information in its separately selected data folder. Do not attach a real case database, report, backup, screenshot, or identifying case information to a public issue.

## Reporting a vulnerability

Use this repository's **Security > Report a vulnerability** facility so the report remains private while it is evaluated. Include the affected application version, a concise reproduction using fictional data, and the security impact.

Do not publicly disclose an unpatched vulnerability or upload real investigative data. Ordinary feature requests and non-sensitive defects may use public GitHub issues.

## Update trust model

The application accepts update metadata only from the public `gdowkpc/traffic-crash-notebook` GitHub release channel. It verifies the declared byte count, SHA-256 digest, ZIP integrity, and required portable files. It does not silently install, extract, launch, or overwrite an update.
