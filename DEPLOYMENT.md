# Zanthalar WebGL deployment

The build repository is `D:\Zanthalar_WebBuild\Zanthalar_WebBuild`.
The AWS testing URL is http://51.21.188.48/.
The repository currently deploys to GitHub Pages automatically on push. AWS deployment is manual.

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

Pushing updates GitHub Pages. Continue with the next step to update AWS.

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
