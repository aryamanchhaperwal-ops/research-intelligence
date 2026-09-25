<#
.SYNOPSIS
    Creates a new research project from the reusable template.

.DESCRIPTION
    Copies templates/research-project/ to projects/<Domain>/<Topic-Slug>/
    and fills in the README metadata. Supports -WhatIf for a dry run.

.PARAMETER Topic
    Short topic label used for titles, e.g. "AI in Healthcare".

.PARAMETER Domain
    One of: technology, society, environment, esg, culture, business, other.
    Default: other.

.PARAMETER KeyQuestion
    Optional key question stored in the project README.

.EXAMPLE
    .\scripts\New-ResearchProject.ps1 -Topic "AI in Healthcare" -Domain technology

.EXAMPLE
    .\scripts\New-ResearchProject.ps1 -Topic "Urban Green Spaces" -Domain environment -KeyQuestion "How do cities compare on green-space access?"
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)]
    [string]$Topic,

    [Parameter(Mandatory = $false)]
    [ValidateSet("technology", "society", "environment", "esg", "culture", "business", "other")]
    [string]$Domain = "other",

    [Parameter(Mandatory = $false)]
    [string]$KeyQuestion = ""
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$template = Join-Path $root "templates\research-project"
$slug = ($Topic -replace '[^a-zA-Z0-9]+', '-').Trim('-').ToLower()
$domainDir = Join-Path $root "projects\$Domain"
$target = Join-Path $domainDir $slug

if (-not (Test-Path -LiteralPath $template)) {
    throw "Template not found: $template"
}

if (Test-Path -LiteralPath $target) {
    throw "Project folder already exists: $target"
}

if (-not (Test-Path -LiteralPath $domainDir)) {
    New-Item -ItemType Directory -Path $domainDir | Out-Null
}

Write-Verbose "Copying template to $target"
if ($PSCmdlet.ShouldProcess($target, "Create project folder from template")) {
    Copy-Item -Path $template -Destination $target -Recurse
}

$today = Get-Date -Format "yyyy-MM-dd"

$readmePath = Join-Path $target "README.md"
if ($PSCmdlet.ShouldProcess($readmePath, "Fill in project metadata")) {
    $readme = Get-Content -LiteralPath $readmePath -Raw
    $readme = $readme -replace '\{Project Title\}', $Topic
    $readme = $readme -replace '\{Topic / short label\}', $Topic
    $readme = $readme -replace '\{technology \| society \| environment \| esg \| culture \| business \| other\}', $Domain
    $readme = $readme -replace '\{YYYY-MM-DD\}', $today
    $readme = $readme -replace '\{scoping \| in progress \| drafting \| complete \| archived\}', "scoping"
    if ($KeyQuestion) {
        $readme = $readme -replace '\{The single question this project answers\.\}', $KeyQuestion
    }
    Set-Content -LiteralPath $readmePath -Value $readme -Encoding UTF8
}

if ($PSCmdlet.ShouldProcess($target, "Log project title/date into PLAN, NOTES, SOURCES")) {
    $planPath = Join-Path $target "PLAN.md"
    $notesPath = Join-Path $target "NOTES.md"
    $sourcesPath = Join-Path $target "SOURCES.md"
    foreach ($p in @($planPath, $notesPath)) {
        if (Test-Path -LiteralPath $p) {
            $c = Get-Content -LiteralPath $p -Raw
            $c = $c -replace '\{Project Title\}', $Topic
            Set-Content -LiteralPath $p -Value $c -Encoding UTF8
        }
    }
    if (Test-Path -LiteralPath $sourcesPath) {
        $c = Get-Content -LiteralPath $sourcesPath -Raw
        $c = $c -replace '\{Project Title\}', $Topic
        Set-Content -LiteralPath $sourcesPath -Value $c -Encoding UTF8
    }
}

Write-Host ""
Write-Host "Project created: $target"
Write-Host "Next steps:"
Write-Host "  1. Review README.md and start PLAN.md"
Write-Host "  2. Log sources in SOURCES.md"
Write-Host "  3. Write findings under findings/ and deliverables under outputs/"