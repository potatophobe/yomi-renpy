# Drives a game window for testing: focus, mouse, keys, screenshots.
# Usage:
#   . utils\gamectl.ps1
#   $script:GameProcess = "renpy"; $script:VW = 1280; $script:VH = 720
#   Focus-Game; Glide-V 400 300; Shot "out.png"
# Coordinates passed to *-V functions are in the game's virtual resolution
# ($script:VW x $script:VH), not in screen pixels.

Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class W {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X, Y; }
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr h, ref POINT p);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(int f, int dx, int dy, int d, IntPtr e);
  [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, int f, IntPtr e);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern uint MapVirtualKey(uint code, uint type);
  [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr h);
}
"@
[W]::SetProcessDPIAware() | Out-Null

# Windows API codes.
$MOUSEEVENTF_LEFTDOWN = 0x0002
$MOUSEEVENTF_LEFTUP = 0x0004
$MOUSEEVENTF_WHEEL = 0x0800
$WHEEL_DELTA = 120              # one wheel notch
$KEYEVENTF_KEYDOWN = 0
$KEYEVENTF_KEYUP = 0x0002
$MAPVK_VK_TO_VSC = 0            # MapVirtualKey: virtual key -> scan code
$SW_RESTORE = 9                 # ShowWindow: restore a minimized window
$VK_MENU = 0x12                 # Alt

# Common virtual keys for Key-Down / Key-Up / Press.
$VK_SHIFT = 0x10
$VK_ESCAPE = 0x1B

# Pauses (milliseconds) that give the game time to see each input.
$MoveDelayMs = 120
$ClickHoldMs = 60
$ClickDelayMs = 300
$WheelDelayMs = 200
$KeyHoldMs = 60
$KeyDelayMs = 250
$FocusDelayMs = 400
$FocusAttempts = 5

# The game being driven: its process name and virtual resolution.
$script:GameProcess = "Katawa Shoujo"
$script:VW = 800
$script:VH = 600

function Get-GameWindow {
  $process = Get-Process | Where-Object { $_.ProcessName -eq $script:GameProcess -and $_.MainWindowHandle -ne 0 } |
    Select-Object -First 1
  if (-not $process) { throw "game window not found" }
  return $process.MainWindowHandle
}

# The window's drawing area in screen pixels.
function Get-Client {
  $window = Get-GameWindow
  $rect = New-Object W+RECT; [W]::GetClientRect($window, [ref]$rect) | Out-Null
  $origin = New-Object W+POINT; [W]::ClientToScreen($window, [ref]$origin) | Out-Null
  return @{ X = $origin.X; Y = $origin.Y; W = $rect.R; H = $rect.B }
}

# Brings the game to the front. Throws if that fails, so that test input is
# never sent to another window.
function Focus-Game {
  $window = Get-GameWindow
  for ($i = 0; $i -lt $FocusAttempts; $i++) {
    if ([W]::GetForegroundWindow() -eq $window) { Start-Sleep -Milliseconds $FocusDelayMs; return }
    # Tapping Alt lets this process change the foreground window.
    [W]::keybd_event($VK_MENU, 0, $KEYEVENTF_KEYDOWN, [IntPtr]::Zero)
    [W]::keybd_event($VK_MENU, 0, $KEYEVENTF_KEYUP, [IntPtr]::Zero)
    [W]::ShowWindow($window, $SW_RESTORE) | Out-Null
    [W]::BringWindowToTop($window) | Out-Null
    [W]::SetForegroundWindow($window) | Out-Null
    Start-Sleep -Milliseconds $FocusDelayMs
  }
  throw "could not focus the game window"
}

function Assert-Focus { if ([W]::GetForegroundWindow() -ne (Get-GameWindow)) { throw "game lost focus" } }

function Move-V([double]$x, [double]$y) {
  # Ren'Py letterboxes the virtual screen inside the window.
  $client = Get-Client
  $scale = [Math]::Min($client.W / $script:VW, $client.H / $script:VH)
  $offsetX = ($client.W - $script:VW * $scale) / 2
  $offsetY = ($client.H - $script:VH * $scale) / 2
  [W]::SetCursorPos([int]($client.X + $offsetX + $x * $scale), [int]($client.Y + $offsetY + $y * $scale)) | Out-Null
  Start-Sleep -Milliseconds $MoveDelayMs
}

# Moves in small steps so the game sees several motion events: these offsets
# (virtual pixels) from the target, approaching from the upper left.
$GlideSteps = @(@(6, 2), @(3, 1), @(0, 0))

function Glide-V([double]$x, [double]$y) {
  foreach ($step in $GlideSteps) { Move-V ($x - $step[0]) ($y - $step[1]) }
}

function Click-V([double]$x, [double]$y) {
  Move-V $x $y
  [W]::mouse_event($MOUSEEVENTF_LEFTDOWN, 0, 0, 0, [IntPtr]::Zero); Start-Sleep -Milliseconds $ClickHoldMs
  [W]::mouse_event($MOUSEEVENTF_LEFTUP, 0, 0, 0, [IntPtr]::Zero); Start-Sleep -Milliseconds $ClickDelayMs
}

# Positive notches scroll up, negative down.
function Wheel([int]$notches) {
  [W]::mouse_event($MOUSEEVENTF_WHEEL, 0, 0, $WHEEL_DELTA * $notches, [IntPtr]::Zero)
  Start-Sleep -Milliseconds $WheelDelayMs
}

# SDL2 reads the scan code, so send it along with the virtual key.
function Get-ScanCode([byte]$key) { [byte][W]::MapVirtualKey($key, $MAPVK_VK_TO_VSC) }
function Key-Down([byte]$key) { Assert-Focus; [W]::keybd_event($key, (Get-ScanCode $key), $KEYEVENTF_KEYDOWN, [IntPtr]::Zero) }
function Key-Up([byte]$key) { [W]::keybd_event($key, (Get-ScanCode $key), $KEYEVENTF_KEYUP, [IntPtr]::Zero) }
function Press([byte]$key) {
  Key-Down $key; Start-Sleep -Milliseconds $KeyHoldMs
  Key-Up $key; Start-Sleep -Milliseconds $KeyDelayMs
}

# Saves the window's drawing area as a PNG.
function Shot([string]$path) {
  $client = Get-Client
  $bitmap = New-Object System.Drawing.Bitmap $client.W, $client.H
  $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
  $graphics.CopyFromScreen($client.X, $client.Y, 0, 0, $bitmap.Size)
  $bitmap.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
  $graphics.Dispose(); $bitmap.Dispose()
}
