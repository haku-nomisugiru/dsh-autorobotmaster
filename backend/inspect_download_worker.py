"""Read references and open a copied model in the existing SolidWorks session."""
import json,sys,traceback
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
from library_inspection import classify_reference,sha256,scope_dependencies

def read(obj,name,*args):
    if name.startswith('Get') and hasattr(obj,'_FlagAsMethod'):obj._FlagAsMethod(name)
    member=getattr(obj,name)
    return member(*args) if callable(member) else member

def inspect(request,repository):
    import pythoncom,pywintypes
    from win32com.client import dynamic
    pythoncom.CoInitialize()
    try:
        app=dynamic.Dispatch(pythoncom.GetActiveObject(pywintypes.IID('SldWorks.Application')).QueryInterface(pythoncom.IID_IDispatch))
        app._FlagAsMethod('GetDocumentDependencies2')
        entry=Path(request['entry_path']);workspace=Path(request['workspace']);files=[p for p in workspace.rglob('*') if p.is_file()]
        report=dict(request,checked_at_utc=datetime.now(timezone.utc).isoformat(),status='running',dependencies=[],dependency_errors=[],components=[],structure_errors=[],configurations=[],inspection_scope='saved direct references of packaged assemblies; active configuration structure only',motion_verified=False,fit_to_target_verified=False,native_mates_verified=False,material_mass_verified=False)
        if sha256(entry)!=request['entry_sha256']:raise ValueError('工作副本哈希变化')
        for owner in files:
            if owner.suffix.lower() not in {'.sldasm','.sldprt'}:continue
            try:
                raw=app.GetDocumentDependencies2(str(owner),False,False,False)
                if not raw:
                    if owner.suffix.lower()=='.sldasm':report['dependency_errors'].append({'owner':str(owner),'error':'no_references_returned'})
                    continue
                if len(raw)%2:raise ValueError('unexpected reference pair count')
                for i in range(0,len(raw),2):
                    item=classify_reference(raw[i+1],owner,files,workspace);item.update(owner=str(owner),name=raw[i]);report['dependencies'].append(item)
            except Exception as error:report['dependency_errors'].append({'owner':str(owner),'error':str(error)[:1000]})
        report['dependency_counts']=dict(Counter(d['status'] for d in report['dependencies']))
        report['status']='opening'
        Path(request['report_path']).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        from win32com.client import VARIANT
        errors=VARIANT(pythoncom.VT_BYREF|pythoncom.VT_I4,0)
        warnings=VARIANT(pythoncom.VT_BYREF|pythoncom.VT_I4,0)
        app._FlagAsMethod('GetOpenDocumentByName')
        model=app.GetOpenDocumentByName(str(entry))
        if model is not None:
            existing_path=read(model,'GetPathName')
            if existing_path and Path(existing_path).resolve()!=entry.resolve():raise ValueError('存在不同路径的同名已打开文件，请先关闭该同名文件：'+existing_path)
        report['reused_open_document']=model is not None
        if model is None:
            if entry.suffix.lower() in {'.step','.stp'}:
                app._FlagAsMethod('GetImportFileData','LoadFile4')
                data=app.GetImportFileData(str(entry))
                if data is None:raise RuntimeError('SolidWorks无法取得STEP导入选项')
                model=app.LoadFile4(str(entry),'r',data,errors)
            else:
                app._FlagAsMethod('OpenDoc6')
                model=app.OpenDoc6(str(entry),2 if entry.suffix.lower()=='.sldasm' else 1,3,'',errors,warnings)
        report['open_errors']=errors.value;report['open_warnings']=warnings.value
        if model is None:raise RuntimeError('SolidWorks did not return a document')
        report['document']={'title':read(model,'GetTitle'),'path':read(model,'GetPathName'),'type':read(model,'GetType'),'in_memory_dirty':read(model,'GetSaveFlag'),'native_read_only_requested':entry.suffix.lower() in {'.sldasm','.sldprt'},'imported_exchange_working_copy':entry.suffix.lower() in {'.step','.stp'}}
        try:report['configurations']=list(read(model,'GetConfigurationNames') or [])
        except Exception as error:report['structure_errors'].append('configurations: '+str(error))
        try:report['active_configuration']=read(read(model,'GetActiveConfiguration'),'Name')
        except Exception as error:report['structure_errors'].append('active_configuration: '+str(error))
        if report['document']['type']==2:
            try:
                components=list(read(model,'GetComponents',False) or [])
                report['component_count']=len(components);report['components_truncated']=len(components)>2000
                for component in components[:2000]:
                    row={}
                    for key,member in [('name','Name2'),('path','GetPathName'),('configuration','ReferencedConfiguration'),('suppression','GetSuppression'),('virtual','IsVirtual')]:
                        try:row[key]=read(component,member)
                        except Exception as error:row[key]=None;row.setdefault('errors',[]).append(member+': '+str(error)[:200])
                    try:
                        parent=read(component,'GetParent');row['parent']=read(parent,'Name2') if parent else None
                        row['loaded']=read(component,'GetModelDoc2') is not None
                    except Exception as error:row['loaded']=None;row.setdefault('errors',[]).append('parent_or_loaded: '+str(error)[:200])
                    row['file_exists']=bool(row.get('path') and Path(row['path']).is_file())
                    row['outside_workspace']=bool(row.get('path') and not Path(row['path']).resolve().is_relative_to(workspace.resolve()))
                    report['components'].append(row)
            except Exception as error:report['structure_errors'].append('components: '+str(error))
        elif report['document']['type']==1:
            try:
                bodies=list(read(model,'GetBodies2',-1,False) or []);report['body_count']=len(bodies);report['body_names']=[read(b,'Name') for b in bodies[:200]]
            except Exception as error:report['structure_errors'].append('bodies: '+str(error))
        scope_dependencies(report)
        report['unloaded_components']=[c.get('name') for c in report['components'] if c.get('loaded') is not True]
        report['external_components']=[c.get('name') for c in report['components'] if c.get('outside_workspace')]
        report['entry_hash_after']=sha256(entry);report['status']='inspected'
        report['limitations']=['仅检查当前配置；压缩、轻化及未加载组件不能直接判定为缺失。','同名候选不等于实际引用已解析；未自动改写或替换引用。','未验证配合、运动、安装接口、材料或质量；打开成功不等于可直接复用。','STEP导入使用独立工作副本；未保存原生修改。','STEP导入可能产生SolidWorks临时路径；文件路径不存在但已加载的组件不能判为缺失。']
        return report
    finally:pythoncom.CoUninitialize()

if __name__=='__main__':
    request=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    try:result=inspect(request,sys.argv[2])
    except Exception as error:
        path=Path(request['report_path']);result=json.loads(path.read_text(encoding='utf-8')) if path.exists() else dict(request)
        result.update(status='failed',error=str(error),traceback=traceback.format_exc())
    Path(request['report_path']).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
