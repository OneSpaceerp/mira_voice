# TextField

A labelled single-line input with an optional hint or error.

- Label always above the field; placeholder is an example, never the label.
- Error text sits under the field, starts with an alert icon, says what happened and what to do ("Can't reach this host. Check the address or the firewall."). Errors use `danger` (terracotta), not the brand red.
- `mono` for phone numbers, extensions, IPs and SIP URIs; those stay LTR inside Arabic forms (`dir="ltr"` on the input).
- 40 px tall on desktop, 48 px (`control-lg`) on touch.
