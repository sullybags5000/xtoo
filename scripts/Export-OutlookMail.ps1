<#
.SYNOPSIS
    Exports Outlook mail to .msg files so Xtoo can index them from WSL.

.DESCRIPTION
    Runs on Windows against a local Outlook profile using COM. Reads mail only; it
    never deletes, moves, or marks messages. Filenames are derived from the message
    entry ID, so re-running the script skips messages that were already exported
    instead of creating duplicates.

.PARAMETER FolderPath
    Folder to export, relative to the mailbox root, for example 'Inbox\Projects'.
    Omit it to choose a folder interactively.

.PARAMETER FolderList
    Text file naming several folders to export, one path from the mailbox root per
    line, such as 'Inbox\Projects'. Blank lines are ignored. Each folder is exported
    on its own into Destination\<path>, so 'Inbox\Projects\Alpha' lands in
    Destination\Inbox\Projects\Alpha, the layout -IncludeSubfolders produces when
    exporting Inbox. A folder that cannot be found is reported and the rest still
    run; the script then exits with code 1. Cannot be combined with -FolderPath.

.PARAMETER Destination
    Directory that receives the .msg files. Point Xtoo at this directory.

.PARAMETER Days
    Only export messages received in the last N days. Use 0 for the whole folder.

.PARAMETER Since
    Only export messages received on or after this date, for example '2025-08-14'.
    Takes precedence over -Days. Use it to top up an export that already covers
    older mail; scripts/mail_coverage.py reports the date each folder stops at.

.PARAMETER IncludeSubfolders
    Also export every folder beneath FolderPath, into matching subdirectories.

.EXAMPLE
    .\Export-OutlookMail.ps1
    Picks a folder interactively and exports the last 90 days.

.EXAMPLE
    .\Export-OutlookMail.ps1 -FolderPath 'Inbox\Projects' -Days 30 -Destination 'C:\Users\me\Documents\MailExport'
    Unattended form, suitable for a scheduled task.

.EXAMPLE
    .\Export-OutlookMail.ps1 -FolderPath 'Inbox\Projects' -Since '2025-07-29' -Destination 'C:\Users\me\Documents\MailExport'
    Tops up a folder that was already exported as far as 29 July 2025.

.EXAMPLE
    .\Export-OutlookMail.ps1 -FolderList 'C:\Users\me\mail-folders.txt' -Days 7 -Destination 'C:\Users\me\Documents\MailExport'
    Exports only the folders named in mail-folders.txt, each into its own subdirectory.
#>

[CmdletBinding()]
param(
    [string]$FolderPath,
    [string]$FolderList,
    [string]$Destination = (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'MailExport'),
    [int]$Days = 90,
    [datetime]$Since = [datetime]::MinValue,
    [switch]$IncludeSubfolders
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$MaxPathLength = 260
$MaxSubjectLength = 100

function Select-FolderInteractively($folders) {
    if ($folders.Count -eq 0) { return $null }
    Write-Host "`nSelect a folder:" -ForegroundColor Cyan
    for ($i = 1; $i -le $folders.Count; $i += 3) {
        $line = ''
        for ($j = 0; $j -lt 3 -and ($i + $j) -le $folders.Count; $j++) {
            $line += '{0,2}. {1,-24}' -f ($i + $j), $folders.Item($i + $j).Name
        }
        Write-Host $line -ForegroundColor Yellow
    }
    Write-Host '0. Export this folder itself' -ForegroundColor Green
    do {
        $choice = Read-Host 'Folder number'
        if ($choice -match '^\d+$' -and [int]$choice -le $folders.Count) { return [int]$choice }
        Write-Host 'Enter one of the numbers listed above.' -ForegroundColor Yellow
    } while ($true)
}

function Get-FolderInteractively($folder) {
    while ($folder.Folders.Count -gt 0) {
        Write-Host "`nCurrent folder: $($folder.Name)" -ForegroundColor Green
        $choice = Select-FolderInteractively $folder.Folders
        if (-not $choice) { break }
        $folder = $folder.Folders.Item($choice)
    }
    return $folder
}

function Resolve-FolderPath($root, [string]$path) {
    $folder = $root
    foreach ($segment in $path.Split('\') | Where-Object { $_.Trim() }) {
        # Outlook allows a folder name to end in a space, which nobody types.
        $child = $folder.Folders | Where-Object { $_.Name.Trim() -eq $segment.Trim() } | Select-Object -First 1
        if (-not $child) { throw "Folder not found: '$segment' in '$($folder.Name)'." }
        $folder = $child
    }
    return $folder
}

function Get-SafeName([string]$name) {
    foreach ($char in [System.IO.Path]::GetInvalidFileNameChars()) {
        # [string] casts pick Replace(string, string); a bare [char] binds an overload
        # that cannot take an empty replacement.
        $name = $name.Replace([string]$char, '')
    }
    return $name.Trim()
}

function Get-EntryTag([string]$entryId) {
    # A stable per-message tag keeps re-runs idempotent and separates identical subjects.
    $sha = [System.Security.Cryptography.SHA1]::Create()
    try {
        $bytes = $sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($entryId))
        return [BitConverter]::ToString($bytes).Replace('-', '').Substring(0, 8).ToLower()
    } finally {
        $sha.Dispose()
    }
}

function Get-ItemDate($item) {
    # Sent Items and drafts may carry no ReceivedTime, and unsent mail reports year 4501.
    $values = @()
    try { $values += $item.ReceivedTime } catch { }
    try { $values += $item.SentOn } catch { }
    try { $values += $item.CreationTime } catch { }
    foreach ($value in $values) {
        if ($value -is [datetime] -and $value.Year -ge 1900 -and $value.Year -le 2400) {
            return $value
        }
    }
    return $null
}

function Export-Folder($folder, [string]$target, [datetime]$cutoff) {
    if (-not (Test-Path -LiteralPath $target)) {
        $null = New-Item -ItemType Directory -Path $target -Force
    }
    $items = $folder.Items
    if ($cutoff -ne [datetime]::MinValue) {
        # Restrict filters inside Outlook and is far faster than walking every item, which
        # in a large folder keeps Outlook busy for minutes. Outlook reads the date literal
        # in the user's locale, which is how the 'g' format writes it. SentOn covers Sent
        # Items, where ReceivedTime may not apply. Every item is still re-checked below.
        try {
            $when = "'" + $cutoff.ToString('g') + "'"
            $items = $items.Restrict("[ReceivedTime] >= $when OR [SentOn] >= $when")
        } catch {
            Write-Verbose 'Restrict was rejected; filtering on the client instead.'
        }
    }

    $exported = 0; $present = 0; $ignored = 0; $failed = 0
    Write-Host "Scanning $($folder.Name)..." -ForegroundColor DarkGray
    foreach ($item in $items) {
        try {
            if ($item.MessageClass -notlike 'IPM.Note*') { $ignored++; continue }
            $received = Get-ItemDate $item
            if (-not $received -or $received -lt $cutoff) { $ignored++; continue }
            $subject = Get-SafeName ([string]$item.Subject)
            if (-not $subject) { $subject = 'no-subject' }
            if ($subject.Length -gt $MaxSubjectLength) {
                $subject = $subject.Substring(0, $MaxSubjectLength)
            }
            $stamp = $received.ToString('yyyyMMdd_HHmmss')
            $tag = Get-EntryTag $item.EntryID
            $file = Join-Path $target ('{0}_{1}_{2}.msg' -f $stamp, $subject, $tag)
            while ($file.Length -gt $MaxPathLength -and $subject.Length -gt 10) {
                $subject = $subject.Substring(0, $subject.Length - 10)
                $file = Join-Path $target ('{0}_{1}_{2}.msg' -f $stamp, $subject, $tag)
            }
            if (Test-Path -LiteralPath $file) { $present++; continue }
            $item.SaveAs($file, 9)  # 9 = olMSGUnicode, which preserves non-ASCII text
            $exported++
            # A large folder takes hours, so report progress rather than going silent.
            if ($exported % 500 -eq 0) {
                Write-Host "  $($folder.Name): $exported exported" -ForegroundColor DarkGray
            }
        } catch {
            $failed++
            Write-Warning "Could not export a message in '$($folder.Name)': $($_.Exception.Message)"
        }
    }
    $summary = '{0,-30} exported {1}, already present {2}, skipped {3}, failed {4}'
    Write-Host ($summary -f $folder.Name, $exported, $present, $ignored, $failed) -ForegroundColor Cyan

    if ($IncludeSubfolders) {
        foreach ($child in $folder.Folders) {
            Export-Folder $child (Join-Path $target (Get-SafeName $child.Name)) $cutoff
        }
    }
}

if ($FolderPath -and $FolderList) { throw 'Use -FolderPath or -FolderList, not both.' }
if ($FolderList) {
    # Read before touching Outlook, so a mistyped list path fails fast.
    $paths = @(Get-Content -LiteralPath $FolderList -Encoding UTF8 | Where-Object { $_.Trim() })
    if ($paths.Count -eq 0) { throw "No folders listed in '$FolderList'." }
}

$namespace = (New-Object -ComObject Outlook.Application).GetNamespace('MAPI')
$root = $namespace.GetDefaultFolder(6).Parent  # mailbox root, so Sent Items is reachable too
$cutoff = if ($Since -gt [datetime]::MinValue) {
    $Since
} elseif ($Days -gt 0) {
    (Get-Date).AddDays(-$Days)
} else {
    [datetime]::MinValue
}
$window = if ($cutoff -eq [datetime]::MinValue) { 'all messages' } else { "from $($cutoff.ToString('yyyy-MM-dd'))" }

if ($FolderList) {
    $missing = @()
    Write-Host "Exporting $($paths.Count) listed folders ($window) to $Destination" -ForegroundColor Green
    foreach ($path in $paths) {
        try {
            $folder = Resolve-FolderPath $root $path
        } catch {
            Write-Warning $_.Exception.Message
            $missing += $path.Trim()
            continue
        }
        $target = $Destination
        foreach ($segment in $path.Split('\') | Where-Object { $_.Trim() }) {
            $target = Join-Path $target (Get-SafeName $segment)
        }
        Export-Folder $folder $target $cutoff
    }
    if ($missing) {
        Write-Host "`nNot found in Outlook, so not exported:" -ForegroundColor Yellow
        $missing | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
        exit 1
    }
    Write-Host "`nDone." -ForegroundColor Green
    return
}

$folder = if ($FolderPath) { Resolve-FolderPath $root $FolderPath } else { Get-FolderInteractively $root }
$target = Join-Path $Destination (Get-SafeName $folder.Name)
Write-Host "Exporting '$($folder.Name)' ($window) to $target" -ForegroundColor Green
Export-Folder $folder $target $cutoff
Write-Host "`nDone. Add this folder to your Xtoo configuration as a WSL path." -ForegroundColor Green
