# tests/sipp/

SIPp scenarios: register, basic call, IVR walk, queue load. Used from task 0.3 (smoke calls) and 2.7 (load test at 2× the pilot's peak).

## trunks/ (task 1.2)

Fake carriers used by `tests/integration/telephony/trunk-calls.sh` (placeholders `@…@` are filled in by the script):

| File | Plays |
| --- | --- |
| `carrier-registrar.xml` | A carrier registrar (like WE): challenges the REGISTER with digest auth, checks the password (`verifyauth`), then answers refreshes. Run with `-aa` so Asterisk's OPTIONS keepalives are answered |
| `carrier-call-in.xml` | A carrier calling in on the Contact Mira registered, with the DID in `To`; also used to send a forged `X-Mira-Trunk` header that must be ignored |
