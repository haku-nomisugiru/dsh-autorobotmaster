"""Prepare isolated model copies and classify saved references without relinking."""
import hashlib,json,ntpath,os,shutil,stat,uuid,zipfile
from pathlib import Path,PurePosixPath

def reserved_name(name):
    reserved={'CON','PRN','AUX','NUL'}|{'COM'+str(i) for i in range(1,10)}|{'LPT'+str(i) for i in range(1,10)}
    return name.split('.')[0].upper() in reserved

def archive_name(member):
    name=member.filename
    if not member.flag_bits & 0x800:
        try:name=name.encode('cp437').decode('gbk')
        except (UnicodeEncodeError,UnicodeDecodeError):pass
    return name.replace('\\','/')

def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(4194304),b''):h.update(chunk)
    return h.hexdigest()

def prepare(root,selection):
    root=Path(root).resolve();source=Path(selection['path']).resolve()
    if not source.is_relative_to(root/'data/library-downloads') or not source.is_file():raise ValueError('模型必须来自本插件下载目录')
    if sha256(source)!=selection['sha256']:raise ValueError('下载文件内容已变化，请重新下载')
    directory=root/'data/library-inspections'/uuid.uuid4().hex
    folder=directory/'files';folder.mkdir(parents=True)
    files=[]
    if source.suffix.lower()=='.zip':
        with zipfile.ZipFile(source) as archive:
            members=archive.infolist();seen=set();total=0
            if len(members)>50000:raise ValueError('压缩包条目超过限制')
            for member in members:
                name=archive_name(member);parts=PurePosixPath(name)
                if parts.is_absolute() or any(p in {'..','.'} or ':' in p or p.endswith((' ','.')) or reserved_name(p) for p in parts.parts):raise ValueError('压缩包路径不安全')
                if stat.S_ISLNK(member.external_attr>>16):raise ValueError('不支持符号链接')
                target=(folder/Path(*parts.parts)).resolve()
                if not target.is_relative_to(folder):raise ValueError('压缩包路径越界')
                key=str(target).casefold()
                if key in seen:raise ValueError('压缩包包含重复或大小写冲突路径')
                seen.add(key);total+=member.file_size
                if total>8*1024**3:raise ValueError('解包超过8GiB限制')
            for member in members:
                target=folder/Path(*PurePosixPath(archive_name(member)).parts)
                if member.is_dir():target.mkdir(parents=True,exist_ok=True);continue
                target.parent.mkdir(parents=True,exist_ok=True)
                with archive.open(member) as src,target.open('xb') as out:shutil.copyfileobj(src,out,1048576)
                files.append(target)
    else:
        name=ntpath.basename(selection['model']['entry']['path'])
        if not name or ':' in name or reserved_name(name):raise ValueError('模型入口文件名无效')
        target=folder/(Path(name).stem+'_'+directory.name[:8]+Path(name).suffix) if source.suffix.lower() in {'.step','.stp'} else folder/name
        shutil.copyfile(source,target);files=[target]
    expected=selection['model']['entry']['sha256'];extension=selection['model']['entry']['extension'].lower()
    matches=[p for p in files if p.suffix.lower()==extension and sha256(p)==expected]
    if len(matches)!=1:raise ValueError('无法唯一定位与模型卡片哈希一致的入口文件：'+str(len(matches)))
    entry=matches[0]
    job={'entry_path':str(entry),'workspace':str(folder),'model_id':selection['model']['id'],'source_url':selection['model'].get('source_url'),'entry_sha256':expected,'download_sha256':selection['sha256'],'report_path':str(directory/'inspection.json')}
    (directory/'request.json').write_text(json.dumps(job,ensure_ascii=False,indent=2),encoding='utf-8')
    return job

def classify_reference(saved_path,owner,files,workspace):
    saved_path=str(saved_path);owner=Path(owner);workspace=Path(workspace).resolve()
    direct=(owner.parent/saved_path).resolve()
    if direct.is_relative_to(workspace) and direct.is_file():return {'saved_path':saved_path,'status':'local_path_found','candidates':[str(direct)]}
    candidates=[str(p) for p in files if p.name.casefold()==ntpath.basename(saved_path).casefold()]
    status='potential_local_match' if len(candidates)==1 else 'ambiguous' if candidates else 'missing_from_package'
    return {'saved_path':saved_path,'status':status,'candidates':candidates}

def ai_evidence(report):
    if not report:return None
    result={k:report.get(k) for k in ['status','model_id','source_url','entry_path','entry_sha256','document','open_errors','open_warnings','configurations','active_configuration','component_count','body_count','body_names','components_truncated','dependency_counts','package_dependency_counts','dependency_errors','structure_errors','unloaded_components','external_components','limitations','error','motion_verified','fit_to_target_verified','native_mates_verified','material_mass_verified','report_path']}
    result['components']=report.get('components',[])[:150]
    result['components_in_prompt_truncated']=len(report.get('components',[]))>150
    result['dependency_issues']=[d for d in report.get('dependencies',[]) if d.get('scope','selected_model')=='selected_model' and d['status'] in {'missing_from_package','ambiguous'}][:150]
    result['dependency_issues_in_prompt_truncated']=sum(d.get('scope','selected_model')=='selected_model' and d['status'] in {'missing_from_package','ambiguous'} for d in report.get('dependencies',[]))>150
    return result

def scope_dependencies(report):
    from collections import Counter
    selected_paths={str(Path(report['entry_path']).resolve()).casefold()}
    selected_paths.update(str(Path(c['path']).resolve()).casefold() for c in report.get('components',[]) if c.get('path'))
    for dependency in report.get('dependencies',[]):
        dependency['scope']='selected_model' if str(Path(dependency['owner']).resolve()).casefold() in selected_paths else 'package_other_files'
    report['package_dependency_counts']=dict(Counter(d['status'] for d in report.get('dependencies',[])))
    report['dependency_counts']=dict(Counter(d['status'] for d in report.get('dependencies',[]) if d['scope']=='selected_model'))
    return report

def reuse_payload(selection,report,target_requirements=''):
    # Dedicated assessment contains no chat history, unrelated projects, absolute paths, or CAD binary.
    if report.get('status')!='inspected':raise ValueError('请先完成实际模型打开检查')
    if report.get('model_id')!=selection['model']['id'] or report.get('download_sha256')!=selection['sha256']:raise ValueError('检查报告与当前下载不一致，请重新检查')
    components=[{k:c.get(k) for k in ['name','parent','configuration','suppression','virtual','loaded','file_exists','outside_workspace']} for c in report.get('components',[])[:150]]
    issues=[{'owner_name':ntpath.basename(d['owner']),'reference_name':ntpath.basename(d['saved_path']),'status':d['status']} for d in report.get('dependencies',[]) if d.get('scope')=='selected_model' and d['status'] in {'missing_from_package','ambiguous'}][:150]
    return {'model':{k:selection['model'].get(k) for k in ['id','name','source_url','verification','limitations']},'target_requirements':str(target_requirements)[:4000],
        'actual_inspection':{k:report.get(k) for k in ['status','checked_at_utc','active_configuration','configurations','component_count','body_count','open_errors','open_warnings','dependency_counts','package_dependency_counts','motion_verified','fit_to_target_verified','native_mates_verified','material_mass_verified','limitations']},
        'components':components,'dependency_issues':issues,'component_list_truncated':len(report.get('components',[]))>150}

REUSE_SCHEMA={'type':'object','additionalProperties':False,'properties':{'decision':{'type':'string','enum':['reference_only','needs_dependencies','needs_target_requirements','needs_engineering_validation']},'summary':{'type':'string'},'evidence':{'type':'array','items':{'type':'string'}},'missing_checks':{'type':'array','items':{'type':'string'}}},'required':['decision','summary','evidence','missing_checks']}
