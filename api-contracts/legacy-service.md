# Legacy Subscriber Service
`POST /api/legacy/subscriber-status`, content type `application/xml`.

```xml
<SubscriberStatusRequest><AccountNumber>ACC-2001</AccountNumber><ServiceNumber>SVC-5001</ServiceNumber></SubscriberStatusRequest>
```

Success returns fields `ACCT_NO`, `SVC_NO`, `SVC_STAT`, `NET_STAT`, `ERR_CD`, and `RESP_TS`. Error codes: 0 success, 101 account missing, 102 service missing, 205 auth rejected, 301 required field missing, 429 rate limited, 503 unavailable, 900 unknown.
