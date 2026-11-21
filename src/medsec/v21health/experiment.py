"""Full container evaluation with reusable clean baselines and source episodes."""
import argparse
import asyncio
import json
import shutil
import uuid
from datetime import datetime,timezone
from pathlib import Path
from ..v08.contracts import ROOT,sha256,tree_hash
from ..v11.memory_suite import write

BASE=ROOT/'data/medsec/v10_expanded_seed0'
MEM=ROOT/'data/medsec/v21health_memory'


def catalog():
    old=json.loads((BASE/'manifest.json').read_text())
    tasks={r['task_id']:{**r,'path':str(BASE/r['harbor_ref'])} for r in old['tasks'] if 'harbor_ref' in r}
    attacks=[{**a,'attack_ref':str(BASE/a['attack_ref']),'attack_root':str(BASE)} for a in old['attacks'] if a['task_id'] in tasks]
    memory=json.loads((MEM/'manifest.json').read_text())
    tasks.update({t['task_id']:t for t in memory['tasks']})
    attacks+=memory['attacks']
    return tasks,attacks


def prepare_case(root,task,condition,attack=None,seed=None):
    case_id='h12-'+sha256(task['task_id']+condition+(attack['attack_id'] if attack else ''))[:18]
    dest=root/'tasks'/case_id
    shutil.copytree(task['path'],dest)
    profile=dict(case_id=case_id,task_id=task['task_id'],condition=condition,defense='scope' if condition.endswith('scope') else 'none',
                 attack_id=attack['attack_id'] if attack else None,attack_path=attack['attack_ref'] if attack else None,
                 attack_root=attack['attack_root'] if attack else None,patient_id=task.get('patient_id',''),project_id=task.get('project_id',''),
                 memory_seed=str(seed) if seed else None,source_task_id=task.get('source_task_id'),
                 original_task_sha256=tree_hash(Path(task['path'])))
    write(dest/'profile.json',profile)
    return dict(profile=profile,path=str(dest),tree_sha256=tree_hash(dest))


async def job(root,name,cases,workers):
    from harbor.models.job.config import JobConfig
    from harbor.job import Job
    config=dict(job_name=name,jobs_dir=str(root/'jobs'),n_concurrent_trials=workers,quiet=True,
                agents=[dict(import_path='src.medsec.v21health.harbor_agent:MedSecHarborAgent',model_name='deepseek-flash',kwargs=dict(max_steps=12))],
                tasks=[dict(path=c['path']) for c in cases])
    write(root/(name+'-config.json'),config)
    instance=await Job.create(JobConfig.model_validate(config))
    await instance.run()


def collect(root,name):
    rows=[]
    for path in sorted((root/'jobs'/name).glob('*/result*.json')):
        if path.name not in {'result.json','results.json'}:
            continue
        result=json.loads(path.read_text())
        config=json.loads((path.parent/'config.json').read_text())
        profile=json.loads((Path(config['task']['path'])/'profile.json').read_text())
        rows.append(dict(profile=profile,result_path=str(path),events_path=str(path.parent/'agent/medsec-events.jsonl'),
                         memory_path=str(path.parent/'agent/memory'),snapshot_path=str(path.parent/'agent/memory-snapshot.json')))
    return rows


async def run(smoke=False,workers=12):
    tasks,attacks=catalog()
    run_id=datetime.now(timezone.utc).strftime('v21health-%Y%m%dT%H%M%SZ-')+uuid.uuid4().hex[:8]
    root=ROOT/'results/medsec'/run_id
    root.mkdir(parents=True,exist_ok=False)
    sources=[t for t in tasks.values() if t.get('role')=='source']
    if smoke:
        sources=sources[:1]
        source_ids={t['task_id'] for t in sources}
        attacks=[next(a for a in attacks if a['surface']==s and a['task_id'].startswith('healthagentbench')) for s in ('malicious_user','skill_file','tool_result','environment_file')]+[next(a for a in attacks if a['surface']=='memory_store_edit' and a['source_task_id'] in source_ids)]
    selected_ids={a['task_id'] for a in attacks}
    write(root/'selection.json',dict(run_id=run_id,smoke=smoke,attacks=attacks,source_task_ids=[t['task_id'] for t in sources],baseline_policy='reuse one clean run per task per defense'))
    source_cases=[prepare_case(root,t,'source_none') for t in sources]
    print(json.dumps(dict(run_id=run_id,phase='source',trials=len(source_cases))),flush=True)
    await job(root,'sources',source_cases,min(workers,len(source_cases)))
    source_results=collect(root,'sources')
    seeds={}
    failed_sources=[]
    for row in source_results:
        result=json.loads(Path(row['result_path']).read_text())
        snapshot=Path(row['snapshot_path'])
        passed=(result.get('verifier_result') or {}).get('rewards',{}).get('reward')==1
        task=tasks[row['profile']['task_id']]
        valid=False
        if snapshot.exists():
            records=[r for rows in json.loads(snapshot.read_text()).values() for r in rows]
            valid=len(records)==1 and records[0]['text']==task['expected_answer'] and records[0]['patient_id']==task['patient_id'] and records[0]['project_id']==task['project_id']
        if passed and valid:
            seeds[task['task_id']]=Path(row['memory_path'])
        else:
            failed_sources.append(task['task_id'])
    cases=[]
    blocked=[]
    for task_id in sorted(selected_ids):
        task=tasks[task_id]
        seed=seeds.get(task.get('source_task_id'))
        if task.get('role')=='target' and seed is None:
            blocked.append(task_id)
            continue
        for defense in ('none','scope'):
            cases.append(prepare_case(root,task,'clean_'+defense,seed=seed))
    for attack in attacks:
        task=tasks[attack['task_id']]
        if task['task_id'] in blocked:
            continue
        seed=seeds.get(task.get('source_task_id'))
        for defense in ('none','scope'):
            cases.append(prepare_case(root,task,'attack_'+defense,attack=attack,seed=seed))
    write(root/'plan.json',dict(run_id=run_id,cases=cases,sources=source_results,failed_sources=failed_sources,blocked_tasks=blocked,requested_attack_count=len(attacks)))
    print(json.dumps(dict(run_id=run_id,phase='targets',trials=len(cases),failed_sources=failed_sources)),flush=True)
    if cases:
        await job(root,'targets',cases,workers)
    from .scoring import freeze_and_score
    report=freeze_and_score(root)
    print(json.dumps(dict(run_id=run_id,report=str(root/'report.json'),summary=report['summary'])),flush=True)
    return root


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--smoke',action='store_true')
    parser.add_argument('--workers',type=int,default=12)
    args=parser.parse_args()
    asyncio.run(run(args.smoke,args.workers))


if __name__=='__main__':
    main()
