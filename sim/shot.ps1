# Capture the simulator window to a PNG so alignment can be checked without
# a human at the screen. Usage: powershell -File shot.ps1 out.png
param([string]$Out = "shot.png")

Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win {
  [DllImport("user32.dll")] public static extern IntPtr FindWindow(string c, string n);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern int GetWindowTextLength(IntPtr h);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, System.Text.StringBuilder s, int m);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr p);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  public delegate bool EnumProc(IntPtr h, IntPtr p);
  public struct RECT { public int Left, Top, Right, Bottom; }
}
"@

# Find the simulator by title prefix rather than an exact match, since the
# title carries the UDP port.
$target = [IntPtr]::Zero
$cb = [Win+EnumProc]{
  param($h, $p)
  if ([Win]::IsWindowVisible($h)) {
    $len = [Win]::GetWindowTextLength($h)
    if ($len -gt 0) {
      $sb = New-Object System.Text.StringBuilder ($len + 1)
      [void][Win]::GetWindowText($h, $sb, $sb.Capacity)
      if ($sb.ToString().StartsWith("ATOM SQ simulator")) { $script:target = $h; return $false }
    }
  }
  return $true
}
[void][Win]::EnumWindows($cb, [IntPtr]::Zero)

if ($target -eq [IntPtr]::Zero) { Write-Output "simulator window not found"; exit 1 }

[void][Win]::SetForegroundWindow($target)
Start-Sleep -Milliseconds 500

$r = New-Object Win+RECT
[void][Win]::GetWindowRect($target, [ref]$r)
$w = $r.Right - $r.Left
$h = $r.Bottom - $r.Top
$bmp = New-Object System.Drawing.Bitmap $w, $h
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($r.Left, $r.Top, 0, 0, $bmp.Size)
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
Write-Output "$Out ($w x $h)"
