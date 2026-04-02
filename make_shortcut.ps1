$path = "$env:USERPROFILE\Desktop\Run Betting Tracker.lnk"
$wshell = New-Object -ComObject Wscript.Shell
$shortcut = $wshell.CreateShortcut($path)
$shortcut.TargetPath = "wscript.exe"
$shortcut.Arguments = "`"c:\Users\Koku\Desktop\betting-tracker\launch.vbs`""
$shortcut.WorkingDirectory = "c:\Users\Koku\Desktop\betting-tracker"
$shortcut.IconLocation = "c:\Users\Koku\Desktop\betting-tracker\static\icon.ico"
$shortcut.WindowStyle = 1
$shortcut.Save()

Write-Host "Shortcut updated successfully on Desktop to run silently"
