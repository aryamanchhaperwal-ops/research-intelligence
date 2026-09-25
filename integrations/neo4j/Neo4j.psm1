#requires -Version 5.1

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$script:Neo4jConnection = $null

function Import-Neo4jEnvironment {
    <#
    .SYNOPSIS
        Loads key=value pairs from a .env file into process environment variables.
        Existing variables are left untouched unless -Force is used.
    #>
    [CmdletBinding(SupportsShouldProcess = $true)]
    param(
        [string]$Path = (Join-Path $PSScriptRoot ".env"),
        [switch]$Force
    )
    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    Get-Content -LiteralPath $Path | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $split = $line.Split('=', 2)
            $key = $split[0].Trim()
            $value = $split[1].Trim().Trim('"').Trim("'")
            $current = [Environment]::GetEnvironmentVariable($key, "Process")
            if ($Force -or ($null -eq $current -or "" -eq $current)) {
                if ($PSCmdlet.ShouldProcess($key, "Set environment variable")) {
                    Set-Item -Path "env:$key" -Value $value
                }
            }
        }
    }
}

function Get-Neo4jConfig {
    <#
    .SYNOPSIS
        Returns merged connection settings: process environment variables
        override config.psd1 defaults. Passwords come only from the
        environment (or are prompted at connect time).
    #>
    [CmdletBinding()]
    param(
        [string]$ConfigPath = (Join-Path $PSScriptRoot "config.psd1")
    )
    Import-Neo4jEnvironment
    if (-not (Test-Path -LiteralPath $ConfigPath)) {
        throw "Config file not found: $ConfigPath"
    }
    $defaults = Import-PowerShellDataFile -LiteralPath $ConfigPath
    $uri = $env:NEO4J_URI
    $user = $env:NEO4J_USER
    $password = $env:NEO4J_PASSWORD
    $database = $env:NEO4J_DATABASE
    $timeout = $env:NEO4J_TIMEOUT_SEC
    if (-not $uri)       { $uri = $defaults.Uri }
    if (-not $user)      { $user = $defaults.User }
    if (-not $database)  { $database = $defaults.Database }
    if (-not $timeout)   { $timeout = $defaults.TimeoutSec }
    $uri = ConvertTo-Neo4jHttpUri $uri
    [pscustomobject]@{
        Uri        = $uri
        User       = $user
        Database   = $database
        Password   = $password
        TimeoutSec = $timeout
        SchemaFile = Join-Path $PSScriptRoot $defaults.SchemaFile
    }
}

function ConvertTo-Neo4jHttpUri {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Uri
    )
    $parsed = [Uri]$Uri
    if ($parsed.Scheme -notin @("neo4j", "bolt", "neo4j+s", "bolt+s")) {
        return $Uri.TrimEnd("/")
    }
    $scheme = if ($parsed.Scheme.EndsWith("+s")) { "https" } else { "http" }
    $port = $parsed.Port
    if ($port -eq 7687 -or $port -eq -1) {
        $port = 7474
    }
    "${scheme}://$($parsed.Host):$port"
}

function Connect-Neo4j {
    <#
    .SYNOPSIS
        Builds and stores a connection object for the current session.
    #>
    [CmdletBinding()]
    param(
        [string]$Uri,
        [string]$User,
        [string]$Password,
        [string]$Database
    )
    $cfg = Get-Neo4jConfig
    if (-not $Uri)      { $Uri = $cfg.Uri }
    if (-not $User)     { $User = $cfg.User }
    if (-not $Database) { $Database = $cfg.Database }
    $pass = $cfg.Password
    if ($Password)      { $pass = $Password }
    if (-not $pass) {
        $secure = Read-Host "Neo4j password for user '$User'" -AsSecureString
        $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        try {
            $pass = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
        }
        finally {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
        }
    }
    $script:Neo4jConnection = @{
        Uri        = $Uri
        User       = $User
        Database   = $Database
        Password   = $pass
        TimeoutSec = $cfg.TimeoutSec
    }
    $script:Neo4jConnection
}

function Invoke-Neo4jCypher {
    <#
    .SYNOPSIS
        Runs a Cypher statement against the transactional HTTP endpoint
        and returns rows as objects whose properties are the column names.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true, Position = 0)]
        [string]$Query,
        [hashtable]$Parameters = @{},
        [string]$Uri,
        [string]$User,
        [string]$Password,
        [string]$Database
    )
    $conn = $script:Neo4jConnection
    if (-not $conn) {
        $conn = Connect-Neo4j
    }
    if ($Uri)      { $conn.Uri = $Uri }
    if ($User)     { $conn.User = $User }
    if ($Password) { $conn.Password = $Password }
    if ($Database) { $conn.Database = $Database }
    $conn.Uri = ConvertTo-Neo4jHttpUri $conn.Uri

    $base = $conn.Uri.TrimEnd('/')
    $endpoint = "$base/db/$($conn.Database)/tx/commit"
    $pair = "$($conn.User):$($conn.Password)"
    $auth = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($pair))
    $headers = @{ Authorization = "Basic $auth" }
    $body = @{
        statements = @(
            @{
                statement = $Query
                parameters = $Parameters
            }
        )
    } | ConvertTo-Json -Depth 10
    $response = Invoke-RestMethod -Uri $endpoint -Method Post -Headers $headers `
        -ContentType "application/json" -Body $body -TimeoutSec $conn.TimeoutSec
    if ($response.errors.Count -gt 0) {
        throw "Neo4j error: $($response.errors[0].message)"
    }
    if ($response.results.Count -eq 0) {
        return
    }
    $result = $response.results[0]
    $result.data | ForEach-Object {
        $row = [ordered]@{}
        for ($i = 0; $i -lt $result.columns.Count; $i++) {
            $row[$result.columns[$i]] = $_.row[$i]
        }
        [pscustomobject]$row
    }
}

function Test-Neo4jConnection {
    <#
    .SYNOPSIS
        Verifies that the graph is reachable and credentials are valid.
    #>
    [CmdletBinding()]
    param(
        [string]$Uri,
        [string]$User,
        [string]$Password,
        [string]$Database
    )
    $rows = Invoke-Neo4jCypher "RETURN 1 AS ok" -Uri $Uri -User $User -Password $Password -Database $Database
    if ($rows[0].ok -eq 1) {
        Write-Host "Connected to $($script:Neo4jConnection.Uri) as $($script:Neo4jConnection.User), database $($script:Neo4jConnection.Database)"
        return $true
    }
    return $false
}

function Initialize-Neo4jSchema {
    <#
    .SYNOPSIS
        Applies schema/schema.cypher (constraints, indexes, seed data).
        Idempotent: safe to run repeatedly.
    #>
    [CmdletBinding()]
    param(
        [string]$SchemaFile = (Join-Path $PSScriptRoot "schema\schema.cypher")
    )
    if (-not (Test-Path -LiteralPath $SchemaFile)) {
        throw "Schema file not found: $SchemaFile"
    }
    $script = Get-Content -LiteralPath $SchemaFile -Raw
    $statements = $script -split ';' | ForEach-Object { $_.Trim() } | Where-Object { $_ }
    foreach ($statement in $statements) {
        Invoke-Neo4jCypher $statement | Out-Null
    }
    Write-Host "Neo4j schema applied from $SchemaFile"
}

Export-ModuleMember -Function `
    Import-Neo4jEnvironment, `
    Get-Neo4jConfig, `
    Connect-Neo4j, `
    Invoke-Neo4jCypher, `
    Test-Neo4jConnection, `
    Initialize-Neo4jSchema