# Helper script to run SSH commands with sshpass via WSL or expect
$pubkey = Get-Content "$env:USERPROFILE\.ssh\id_rsa.pub"
$cmd = "mkdir -p ~/.ssh && echo '$pubkey' >> ~/.ssh/authorized_keys && chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys && echo 'KEY_INSTALLED_OK'"

# Try using plink if available, otherwise use expect approach
Write-Host "Attempting to copy SSH key to Jetson..."
Write-Host "Please run this command manually in your terminal:"
Write-Host ""
Write-Host "ssh pmoraga@192.168.1.61 `"$cmd`""
Write-Host ""
Write-Host "Enter password: Martiluc1317"
