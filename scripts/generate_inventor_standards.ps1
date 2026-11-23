# Original project code; use installed Autodesk Content Center stock families.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [string]$SelectionFile
)
$ErrorActionPreference='Stop'
if([Threading.Thread]::CurrentThread.ApartmentState -ne 'STA'){throw 'Use Windows PowerShell -STA'}
$output=[IO.Path]::GetFullPath($OutputDirectory)
if(Test-Path -LiteralPath $output){throw 'Choose a fresh output directory'}
[void][IO.Directory]::CreateDirectory($output)
$report=[ordered]@{schema_version='uchuva.content_center_generation/1';status='starting';started_utc=[DateTime]::UtcNow.ToString('o');families=[Collections.Generic.List[object]]::new();members=[Collections.Generic.List[object]]::new();issues=[Collections.Generic.List[object]]::new();limitations=@('Generated Content Center members are new library-derived equivalents, not the original referenced files or identities','No source assembly is changed by this script')}
function Save-Report {
    $json=$report|ConvertTo-Json -Depth 30
    for($attempt=0;$attempt -lt 10;$attempt++){
        try{[IO.File]::WriteAllText((Join-Path $output 'content_center.json'),$json,[Text.UTF8Encoding]::new($true));return}
        catch{if($attempt -eq 9){throw};Start-Sleep -Milliseconds 100}
    }
}
function Visit-Node($node){
    foreach($family in $node.Families){
        if($family.DisplayName -notmatch '^BS 290 SKF|^DIN 6885-1 A$|^ISO 10642'){continue}
        $record=[ordered]@{display_name=[string]$family.DisplayName;standard=[string]$family.Standard;path=[string]$node.FullTreeViewPath;internal_name=[string]$family.InternalName;content_identifier=[string]$family.ContentIdentifier;library=[string]$family.LibraryName;library_internal_name=[string]$family.LibraryInternalName;revision_id=[string]$family.RevisionId;is_custom=[bool]$family.IsCustom;columns=@();rows=@()}
        $columns=@();$columnIndex=0
        foreach($column in $family.TableColumns){$columnIndex++;$columns+=@{index=$columnIndex;name=[string]$column.InternalName;heading=[string]$column.DisplayHeading;units=[string]$column.Units;is_custom=[bool]$column.IsCustom}}
        $record.columns=$columns
        $rows=[Collections.Generic.List[object]]::new()
        foreach($row in $family.TableRows){
            $values=[ordered]@{}
            foreach($column in $columns){try{$values[$column.name]=$row.GetCellValue($column.index)}catch{$values[$column.name]=$null}}
            [void]$rows.Add(@{index=[int]$row.Index;internal_name=[string]$row.InternalName;content_identifier=[string]$row.ContentIdentifier;values=$values})
        }
        $record.rows=@($rows);[void]$report.families.Add($record);Save-Report
    }
    foreach($child in $node.ChildNodes){Visit-Node $child}
}
$application=$null;$ownedProcess=$null;$exitCode=2
try{
    if(@(Get-Process -Name Inventor -ErrorAction SilentlyContinue).Count){throw 'Inventor already running; refusing user process access'}
    $application=New-Object -ComObject Inventor.Application
    $application.Visible=$false;$application.SilentOperation=$true
    $processes=@(Get-Process -Name Inventor -ErrorAction SilentlyContinue)
    if($processes.Count -ne 1){throw 'Cannot establish exclusive process ownership'}
    $ownedProcess=$processes[0]
    $report.inventor=@{version=$application.SoftwareVersion.DisplayVersion;process_id=$ownedProcess.Id;private_com_instance=$true}
    $report.status='reading_installed_content_center';Save-Report
    if(-not $SelectionFile){Visit-Node $application.ContentCenter.TreeViewTopNode;$report.status='catalogued_installed_families';$exitCode=0}
    else{
        $selection=Get-Content -LiteralPath $SelectionFile -Raw|ConvertFrom-Json
        $project=$application.DesignProjectManager.DesignProjects.Add(36353,'generated_standards',$output)
        $project.ContentCenterPath=Join-Path $output 'library_cache'
        [void][IO.Directory]::CreateDirectory($project.ContentCenterPath)
        $project.Activate($false)
        $report.project_path=$project.FullFileName
        $report.status='generating_stock_members';Save-Report
        foreach($item in $selection.members){
            $record=[ordered]@{requested_basename=$item.requested_basename;status='creating';selection=$item;provenance='GeneratedContentCenter';original_document_identity_preserved=$false}
            [void]$report.members.Add($record);Save-Report
            try{
                $family=$application.ContentCenter.GetContentObject([string]$item.family_content_identifier)
                $row=$application.ContentCenter.GetContentObject([string]$item.row_content_identifier)
                if([string]$family.RevisionId -ne $item.family_revision_id){throw 'Family revision differs from inspected selection'}
                $record.library_name=[string]$family.LibraryName;$record.family_name=[string]$family.DisplayName
                [int]$reason=0;[string]$message=''
                $path=$family.CreateMember($row,[ref]$reason,[ref]$message,3,$false)
                $record.failure_reason=$reason;$record.failure_message=$message
                if(-not $path -or -not [IO.File]::Exists($path)){throw ('CreateMember did not produce a file: '+$message)}
                if(-not [IO.Path]::GetFullPath($path).StartsWith($output+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Content Center returned a path outside the private output project'}
                $record.generated_file=$path
                $document=$application.Documents.Open($path,$false)
                try{$record.generated_internal_name=[string]$document.InternalName;$record.bounds_cm=@($document.ComponentDefinition.RangeBox.MinPoint.X,$document.ComponentDefinition.RangeBox.MinPoint.Y,$document.ComponentDefinition.RangeBox.MinPoint.Z,$document.ComponentDefinition.RangeBox.MaxPoint.X,$document.ComponentDefinition.RangeBox.MaxPoint.Y,$document.ComponentDefinition.RangeBox.MaxPoint.Z)}finally{$document.Close($true)}
                $stream=[IO.File]::OpenRead($path);$hasher=[Security.Cryptography.SHA256]::Create()
                try{$record.sha256=([BitConverter]::ToString($hasher.ComputeHash($stream))).Replace('-','').ToLowerInvariant()}finally{$stream.Dispose();$hasher.Dispose()}
                $record.status='generated_stock_equivalent'
            }catch{$record.status='failed';$record.error=$_.Exception.Message;[void]$report.issues.Add($_.Exception.Message)}
            Save-Report
        }
        $report.status=if($report.issues.Count){'partial_generation'}else{'generated_stock_equivalents'}
        if(-not $report.issues.Count){$exitCode=0}
    }
}catch{[void]$report.issues.Add($_.Exception.Message);$report.status='blocked'}
finally{
    if($null -ne $application -and $null -ne $ownedProcess){try{for($i=$application.Documents.Count;$i -ge 1;$i--){$application.Documents.Item($i).Close($true)};$application.Quit()}catch{[void]$report.issues.Add($_.Exception.Message)}}
    $report.finished_utc=[DateTime]::UtcNow.ToString('o');Save-Report
}
Write-Output ('Content Center report: '+(Join-Path $output 'content_center.json'))
exit $exitCode
