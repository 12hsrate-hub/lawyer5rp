# Domain Rollout: `lawyer5rp.online` + `lawyer5rp.su`

## Target scheme

- `www.lawyer5rp.online` and `lawyer5rp.online`
  - direct origin access
  - intended primary path for users in Russia
- `www.lawyer5rp.su` and `lawyer5rp.su`
  - proxied through Cloudflare
  - intended public path outside Russia

## DNS

### Cloudflare zone for `lawyer5rp.su`

- `A @ -> 89.111.153.129` with `Proxied`
- `A www -> 89.111.153.129` with `Proxied`

### Direct origin for `lawyer5rp.online`

- keep existing A-records pointing to `89.111.153.129`
- do not redirect `.online` to `.su`

## nginx shape

Keep each domain family independent:

- `http://lawyer5rp.online` -> `https://www.lawyer5rp.online`
- `https://lawyer5rp.online` -> `https://www.lawyer5rp.online`
- `http://lawyer5rp.su` -> `https://www.lawyer5rp.su`
- `https://lawyer5rp.su` -> `https://www.lawyer5rp.su`

Do not redirect:

- `.online` -> `.su`
- `.su` -> `.online`

## Example nginx layout

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name lawyer5rp.online;
    return 308 https://www.lawyer5rp.online$request_uri;
}

server {
    listen 80;
    listen [::]:80;
    server_name lawyer5rp.su;
    return 308 https://www.lawyer5rp.su$request_uri;
}

server {
    listen 443 ssl;
    listen [::]:443 ssl ipv6only=on;
    server_name lawyer5rp.online;
    ssl_certificate /etc/letsencrypt/live/www.lawyer5rp.online/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/www.lawyer5rp.online/privkey.pem;
    return 308 https://www.lawyer5rp.online$request_uri;
}

server {
    listen 443 ssl;
    listen [::]:443 ssl ipv6only=on;
    server_name lawyer5rp.su;
    ssl_certificate /etc/letsencrypt/live/www.lawyer5rp.su/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/www.lawyer5rp.su/privkey.pem;
    return 308 https://www.lawyer5rp.su$request_uri;
}

server {
    listen 443 ssl;
    listen [::]:443 ssl ipv6only=on;
    server_name www.lawyer5rp.online www.lawyer5rp.su;

    ssl_certificate /etc/letsencrypt/live/www.lawyer5rp.online/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/www.lawyer5rp.online/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

## Cloudflare

Recommended start:

- plan: `Free`
- SSL mode: `Full (strict)`
- `Always Use HTTPS`
- keep WAF/bot settings conservative at first

Optional later:

- Worker on `lawyer5rp.su` to redirect `RU` visitors to `https://www.lawyer5rp.online`

## Rollout checklist

1. Wait until `lawyer5rp.su` becomes `Active` in Cloudflare.
2. Confirm `A @` and `A www` in Cloudflare point to `89.111.153.129`.
3. Add `lawyer5rp.su` and `www.lawyer5rp.su` to nginx without cross-domain redirect.
4. Obtain/verify TLS certificate for `www.lawyer5rp.su`.
5. Reload nginx and test:
   - `https://www.lawyer5rp.online/login`
   - `https://www.lawyer5rp.su/login`
6. Check login, static files, and redirect behavior on both domains.
