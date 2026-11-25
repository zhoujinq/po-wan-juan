[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Low')]
param(
    [string]$DataRoot,
    [ValidatePattern('^([01]\d|2[0-3]):[0-5]\d$')]
    [string]$Time = '22:00',
    [switch]$ShowReminder,
    [switch]$PrintPrompt,
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'
$TaskName = '破万卷-每日投喂提醒'

function Get-FeedPrompt {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Day
    )

    # 投喂提示词：与“逐条出阅读卡片，再写日摘”的流程保持一致。
    return @"
请使用破万卷处理我今天发给你的微信聊天记录：出阅读卡片＋日摘。

1. 先将原始记录原样保存到：$Root\inbox\$Day.md（不改写原文）。
2. 按条拆分并去重，逐条按载体阅读；读不到的也保留卡片并如实写明状态，不假装读过。
3. 每条出一张阅读卡片，保存到：$Root\cards\$Day\ ；再写今日日摘：$Root\daily\$Day.md，分隔线前正文不超过400字。
4. 没有知识地图时，「与知识地图的关系」和「与你何干」都写「地图未就绪」，不要编造。
5. 如果今天是周日，再按 ISO-8601 周完成周总结，只推荐一篇最值得我亲自读的文章。

下面我粘贴今日记录：
"@
}

function Show-NativeReminder {
    param([Parameter(Mandatory = $true)][string]$Root)

    Add-Type -AssemblyName System.Windows.Forms
    $prompt = Get-FeedPrompt -Root $Root -Day (Get-Date -Format 'yyyy-MM-dd')
    $message = "今晚的记录，不必都由你读。`n`n请把今天的微信聊天记录粘贴给你的 Agent。点击确定后会复制一段投喂提示词；没有新内容时可以直接略过。"
    $choice = [System.Windows.Forms.MessageBox]::Show(
        $message,
        '破万卷 · 今日投喂',
        [System.Windows.Forms.MessageBoxButtons]::OKCancel,
        [System.Windows.Forms.MessageBoxIcon]::Information
    )
    if ($choice -eq [System.Windows.Forms.DialogResult]::OK) {
        try {
            [System.Windows.Forms.Clipboard]::SetText($prompt)
            [void][System.Windows.Forms.MessageBox]::Show(
                '投喂提示词已复制。请打开 Agent，粘贴提示词和今日记录。',
                '破万卷',
                [System.Windows.Forms.MessageBoxButtons]::OK,
                [System.Windows.Forms.MessageBoxIcon]::Information
            )
        }
        catch {
            [void][System.Windows.Forms.MessageBox]::Show(
                "剪贴板暂时不可用。请直接告诉 Agent：使用破万卷处理今日投喂。`n`n数据目录：$Root",
                '破万卷 · 请手动投喂',
                [System.Windows.Forms.MessageBoxButtons]::OK,
                [System.Windows.Forms.MessageBoxIcon]::Warning
            )
        }
    }
}

if ($PrintPrompt) {
    if (-not $DataRoot) {
        $DataRoot = Join-Path ([Environment]::GetFolderPath('MyDocuments')) '破万卷'
    }
    # 只打印投喂提示词：不弹窗、不创建计划任务，也不创建任何目录。
    [Console]::OutputEncoding = New-Object -TypeName System.Text.UTF8Encoding -ArgumentList $false
    Write-Output (Get-FeedPrompt -Root $DataRoot -Day (Get-Date -Format 'yyyy-MM-dd'))
    exit 0
}

if ($ShowReminder) {
    if (-not $DataRoot) {
        $DataRoot = Join-Path ([Environment]::GetFolderPath('MyDocuments')) '破万卷'
    }
    Show-NativeReminder -Root $DataRoot
    exit 0
}

if ($Uninstall) {
    if ($PSCmdlet.ShouldProcess($TaskName, '移除每日投喂提醒，不删除个人数据')) {
        $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if ($existing) {
            $existing | Unregister-ScheduledTask -Confirm:$false
            Write-Output "已移除任务：$TaskName。个人数据未删除。"
        }
        else {
            Write-Output "任务不存在：$TaskName。个人数据未改动。"
        }
    }
    exit 0
}

if (-not $DataRoot) {
    throw '请通过 -DataRoot 指定破万卷个人数据目录。'
}
if (-not $IsWindows -and $PSVersionTable.PSEdition -eq 'Core') {
    throw 'Windows 原生提醒只能在 Windows 上安装。'
}

$resolvedRoot = $PSCmdlet.GetUnresolvedProviderPathFromPSPath($DataRoot)
$runtimeDir = Join-Path $resolvedRoot 'runtime'
$runtimeScript = Join-Path $runtimeDir 'daily-reminder.ps1'
$engine = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$actionArguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}" -ShowReminder -DataRoot "{1}"' -f $runtimeScript, $resolvedRoot
$at = [datetime]::ParseExact($Time, 'HH:mm', [Globalization.CultureInfo]::InvariantCulture)

if ($PSCmdlet.ShouldProcess($TaskName, "创建或更新每天 $Time 的当前用户提醒")) {
    New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
    Copy-Item -LiteralPath $PSCommandPath -Destination $runtimeScript -Force

    $action = New-ScheduledTaskAction -Execute $engine -Argument $actionArguments
    $trigger = New-ScheduledTaskTrigger -Daily -At $at
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    $principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited

    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description '破万卷：每天提醒用户把今日微信聊天记录交给 Agent。' -Force | Out-Null
    Write-Output "已创建或更新任务：$TaskName"
    Write-Output "执行时间：每天 $Time（当前用户登录时）"
    Write-Output "提醒脚本：$runtimeScript"
    Write-Output '卸载：使用同一脚本并添加 -Uninstall；不会删除个人数据。'
}
