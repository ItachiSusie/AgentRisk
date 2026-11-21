"""Container evaluation (v24): wrong_patient analog; model-parameterized for
cross-model calibration. Standalone tasks, reusable clean baselines."""
import argparse
import asyncio
import json
import shutil
import uuid
from datetime import datetime,timezone
from pathlib import Path
from ..v08.contracts import ROOT,sha256,tree_hash
from ..v11.memory_suite import write

SUITE=ROOT/'data/medsec/v24health_memory'


def catalog():
    man=json.loads((SUITE/'manifest.json').read_text())
    tasks={t['task_id']:t for t in man['tasks']}
    attacks=[dict(a) for a in man['attacks']]
    return tasks,attacks


def prepare_case(root,task,condition,attack=None,seed=None):
    case_id='h24-'+sha256(task['task_id']+condition+(attack['attack_id'] if attack else ''))[:18]
    dest=root/'tasks'/case_id
    shutil.copytree(task['path'],dest)
    profile=dict(case_id=case_id,task_id=task['task_id'],condition=condition,defense='scope' if condition.endswith('scope') else 'none',
                 attack_id=attack['attack_id'] if attack else None,attack_path=attack['attack_ref'] if attack else None,
                 attack_root=attack['attack_root'] if attack else None,patient_id=task.get('patient_id',''),project_id=task.get('project_id',''),
                 memory_seed=str(seed) if seed else None,source_task_id=task.get('source_task_id'),
                 original_task_sha256=tree_hash(Path(task['path'])))
    write(dest/'profile.json',profile)
    return dict(profile=profile,path=str(dest),tree_sha256=tree_hash(dest))


async def job(root,name,cases,workers,model):
    from harbor.models.job.config import JobConfig
    from harbor.job import Job
    config=dict(job_name=name,jobs_dir=str(root/'jobs'),n_concurrent_trials=workers,quiet=True,
                agents=[dict(import_path='src.medsec.v24health.harbor_agent:MedSecHarborAgent',model_name=model,kwargs=dict(max_steps=12))],
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


async def run(smoke=False,workers=12,model='deepseek-flash'):
    tasks,attacks=catalog()
    slug=''.join(c if c.isalnum() else '-' for c in model)[:24]
    run_id=datetime.now(timezone.utc).strftime('v24health-%Y%m%dT%H%M%SZ-')+slug+'-'+uuid.uuid4().hex[:6]
    root=ROOT/'results/medsec'/run_id
    root.mkdir(parents=True,exist_ok=False)
    if smoke:
        attacks=[next(a for a in attacks if a['surface']==s) for s in ('environment_file','tool_result','skill_file','malicious_user')]
    selected_ids={a['task_id'] for a in attacks}
    write(root/'selection.json',dict(run_id=run_id,smoke=smoke,model=model,attacks=attacks,
                                      baseline_policy='reuse one clean run per task per defense'))
    cases=[]
    for task_id in sorted(selected_ids):
        task=tasks[task_id]
        for defense in ('none','scope'):
            cases.append(prepare_case(root,task,'clean_'+defense))
    for attack in attacks:
        task=tasks[attack['task_id']]
        for defense in ('none','scope'):
            cases.append(prepare_case(root,task,'attack_'+defense,attack=attack))
    write(root/'plan.json',dict(run_id=run_id,model=model,cases=cases,sources=[],failed_sources=[],blocked_tasks=[],requested_attack_count=len(attacks)))
    print(json.dumps(dict(run_id=run_id,model=model,phase='targets',trials=len(cases))),flush=True)
    if cases:
        await job(root,'targets',cases,workers,model)
    from .scoring import freeze_and_score
    report=freeze_and_score(root)
    print(json.dumps(dict(run_id=run_id,report=str(root/'report.json'),summary=report['summary'])),flush=True)
    return root


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--smoke',action='store_true')
    parser.add_argument('--workers',type=int,default=12)
    parser.add_argument('--model',default='deepseek-flash',help='model_name for the bridge; re-run per model for cross-model calibration')
    args=parser.parse_args()
    asyncio.run(run(args.smoke,args.workers,args.model))


if __name__=='__main__':
    main()
