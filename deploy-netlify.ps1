# ادخل التوكن هنا:
$env:NETLIFY_AUTH_TOKEN = "YOUR_TOKEN_HERE"

npx netlify-cli deploy --prod --dir="$PSScriptRoot\static"
