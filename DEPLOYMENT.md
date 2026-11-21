# Zanthalar WebGL deployment

The build repository is `D:\Zanthalar_WebBuild\Zanthalar_WebBuild`.
The AWS testing URL is http://51.21.188.48/.
The repository includes GitHub Actions workflows for GitHub Pages and AWS.

## Automatic AWS deployment after push

One-time setup in GitHub: open this repository's Settings, Secrets and variables, Actions. Add repository secret `EC2_SSH_KEY` with the complete contents of the protected EC2 private-key file. Never commit the key or paste it into task comments.

After copying a complete new Unity build into this repository, commit and push `main`. Open Actions and select **Deploy WebGL to AWS** to monitor the deployment. It can also be run manually from the Actions page. The workflow requires successful repository write access and the SSH secret before its first deployment.

The workflow selects only the build files referenced by `index.html`, prepares compression, verifies checksums on EC2, and switches the same live URL to the new release. A failed upload leaves the active release in place. Activation failure restores the previous release. Older managed static releases are removed after successful activation while the current and previous releases are retained. The API/database have independent deployments.

Live URL: http://51.21.188.48/zanthalar/

Automatic deployment setup is ready in code. Verify a successful Actions run before relying on unattended deployment. The manual fallback follows below.

## 1. Make the Unity build

Use the frontend branch containing the WebGL same-origin API fix (`5a24fc40`, initially on `codex/webgl-optimization`).
Build WebGL into a fresh output folder. This avoids including stale files from previous builds.

Copy `index.html`, `Build` and `TemplateData` into this build repository. Keep the filenames referenced by `index.html` together with that exact build. Copy `StreamingAssets` too if a future build produces it.

The build used for the first AWS deployment was generated in `C:\Users\MudassarShaheen\Desktop\ZanthalarWebGL-AWS`. Its active files were copied here with the `Zanthalar_WebBuild` filename prefix.

## 2. Commit and push

In GitHub Desktop, review this build repository, commit the updated build and push to `main`.
Git LFS must upload the actual large files successfully. `.gitattributes` already tracks data and Wasm files.

Copy the full commit SHA from GitHub, or run this locally in PowerShell.

```powershell
git -C "D:\Zanthalar_WebBuild\Zanthalar_WebBuild" rev-parse HEAD
```

After the SSH secret is configured, pushing updates both GitHub Pages and AWS through their workflows. For manual AWS deployment, continue below.

## 3. Connect to AWS

Run this in PowerShell.

```powershell
ssh -i "D:\ZanthalarAccess\Keys\zanthalar-new.pem" ec2-user@51.21.188.48
```

The key is private. Store its backup securely outside Git.

## 4. Download the pushed build on AWS

Check free space with `df -h /`. Keep space for both the current and new release.
Replace the example value below with the full 40-character commit SHA you just pushed.
Run these commands in the SSH terminal.

```bash
COMMIT=PASTE_FULL_COMMIT_SHA_HERE
RELEASE=/var/www/zanthalar-web/$COMMIT
sudo install -d -m 755 -o ec2-user -g ec2-user "$RELEASE"
python3 - "$COMMIT" "$RELEASE" <<'PY'
import hashlib
import json
from pathlib import Path
import re
import sys
import urllib.request

commit, destination = sys.argv[1:]
if not re.fullmatch(r'[0-9a-f]{40}', commit):
    raise SystemExit('Use the full commit SHA from GitHub')
repo = 'mudasaranabitech-crypto/Zanthalar_WebBuild'
root = Path(destination)
raw = f'https://raw.githubusercontent.com/{repo}/{commit}/'
tree_url = f'https://api.github.com/repos/{repo}/git/trees/{commit}?recursive=1'
with urllib.request.urlopen(tree_url, timeout=30) as response:
    tree = json.load(response)['tree']
with urllib.request.urlopen(raw + 'index.html', timeout=30) as response:
    html = response.read()
names = re.findall(r'buildUrl \+ "/([^"/]+)"', html.decode())
if not names:
    raise SystemExit('Inspect the new index.html build paths before deploying')
files = ['index.html'] + ['Build/' + name for name in names]
files += [item['path'] for item in tree
          if item['type'] == 'blob'
          and item['path'].startswith(('TemplateData/', 'StreamingAssets/'))]
for name in files:
    target = root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(raw + name, timeout=60) as response:
        initial = response.read(1024)
        if initial.startswith(b'version https://git-lfs.github.com/spec/v1'):
            pointer = initial.decode()
            expected = re.search(r'oid sha256:([0-9a-f]{64})', pointer).group(1)
            url = f'https://media.githubusercontent.com/media/{repo}/{commit}/{name}'
            with urllib.request.urlopen(url, timeout=120) as asset:
                with target.open('wb') as output:
                    while chunk := asset.read(1024 * 1024):
                        output.write(chunk)
            digest = hashlib.sha256()
            with target.open('rb') as check:
                while chunk := check.read(1024 * 1024):
                    digest.update(chunk)
            actual = digest.hexdigest()
            if actual != expected:
                raise SystemExit('LFS checksum failed for ' + name)
        else:
            with target.open('wb') as output:
                output.write(initial)
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
    print('Downloaded', name)
print('Download complete. Switch releases only after this succeeds.')
PY
```

This downloads a specific version directly from GitHub. It preserves the running release while the download completes. The script assumes the repository remains public and uses the existing Unity template's `buildUrl` format.

## 5. Activate the release

After all downloads succeed, run these in the same SSH terminal.

```bash
readlink /var/www/zanthalar-web/current
sudo nginx -t
sudo ln -s "$RELEASE" /var/www/zanthalar-web/current.next
sudo mv -Tf /var/www/zanthalar-web/current.next /var/www/zanthalar-web/current
```

Record the previous `readlink` output for rollback. Nginx serves the new files immediately through the `current` symlink.

Open http://51.21.188.48/ and hard-refresh with Ctrl+Shift+R. Check loading, login, Adventure and gameplay. Browser requests should use `/api/` and `/ws/` on the same page host and port. The compiled WebGL API fix must be included for this routing to work.

## 6. Roll back if needed

Use the previous release path recorded before activation.

```bash
sudo ln -s /var/www/zanthalar-web/PREVIOUS_RELEASE /var/www/zanthalar-web/current.next
sudo mv -Tf /var/www/zanthalar-web/current.next /var/www/zanthalar-web/current
```

## Hosting details

- Nginx configuration is `/etc/nginx/conf.d/zanthalar-web.conf`.
- Nginx serves the browser build on port 80 and proxies `/api/` and `/ws/` to `127.0.0.1:5000`.
- The backend source and database have separate deployment procedures.
- The first release uses uncompressed build files with Nginx gzip transfer. Gzip build files also have matching Content-Encoding handlers configured.
- TLS/HTTPS is pending. The current HTTP AWS testing link works independently of the GitHub Pages HTTPS address.
- GitHub Pages still needs an HTTPS API and appropriate cross-origin permissions before that separate website can log in.
- On 20 November, HTTP assets and API/WebSocket authentication responses were verified. Automated browser loading was blocked locally by `ERR_BLOCKED_BY_CLIENT`. Authenticated browser gameplay still needs verification.

## Issues encountered and fixes

- **HTTP connection timed out**. Port 80 initially needed an inbound security-group rule. Later intermittent timeouts recovered while the server remained responsive locally. Their exact network cause is unconfirmed.
- **HTTPS connection timed out**. Port 443/TLS is unconfigured. The current testing URL is explicitly `http://51.21.188.48/zanthalar/`.
- **Wasm fetching failed**. A regex Wasm location took priority over the game subfolder rewrite, returning 404. The Nginx prefix must use `location ^~ /zanthalar/` so rewriting happens before the Wasm handler. Verify the full subfolder asset URL, not only `/Build/`.
- **Browser API access**. Ports 80 and 5000 are different origins. The WebGL client now uses the page origin when its hostname matches the configured backend hostname. Nginx forwards `/api/` and `/ws/`.
- **Long first load**. The deployed data file is approximately 115.4 MiB compressed and Wasm is 11.4 MiB compressed. A measured Wasm download took 52.8 seconds. A slow connection can therefore require around ten minutes for the first full load. Page HTTP 200 alone does not establish playable loading.
- **Compression and loading progress**. The active release has precompressed `.gz` sidecars and Nginx `gzip_static on`. Responses supply compressed Content-Length, correct Content-Encoding and Wasm MIME type. Future releases without sidecars still use dynamic gzip. Check disk space before generating sidecars.
- **Low disk space**. Archived journal cleanup freed 252.9 MiB. Retaining old releases and upload packages consumes additional space. Preserve required rollback backups when planning cleanup.
- **Repository push rejected**. The active credential account lacked repository permission. AWS was updated directly over SSH. Local commits still need an authenticated push with the correct account.

The full public Wasm download was checked against the local build SHA256 after the route fix. Login and a complete gameplay session remain pending browser verification.
