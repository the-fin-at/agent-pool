"""Public queue/worker contract behind the quota-aware execution skill."""
import tempfile
import time
import unittest
from pathlib import Path
from agent_pool.providers import Outcome
from agent_pool.store import Store
from agent_pool.worker import tick


class PoolRoutingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.now=time.time()
        self.store=Store(self.root/'pool')
        for name in ['a','b']:
            self.store.add_profile(name,'codex','codex')
            self.store.update_profile(name,enabled=True,checked_at=self.now)

    def tearDown(self):
        self.store.close();self.tmp.cleanup()

    def windows(self,name,five=10,week=10,five_reset=30,week_reset=600):
        self.store.set_windows(name,[{'key':'codex:primary','bucket':'codex','minutes':300,'used':five,'reset':self.now+five_reset},
                                    {'key':'codex:secondary','bucket':'codex','minutes':10080,'used':week,'reset':self.now+week_reset}])

    def submit(self,**kwargs):
        return self.store.submit('Read-only task',self.root,'codex',key='one-job',**kwargs)

    def run_tick(self,runner,now=None,probe=lambda *a:[]):
        with self.store.worker_lock():return tick(self.store,runner=runner,probe=probe,now=self.now if now is None else now)

    def test_full_five_hour_profile_is_skipped_for_free_profile(self):
        self.windows('a',five=100,week_reset=300);self.windows('b',week_reset=600)
        job=self.submit();chosen=[]
        self.run_tick(lambda p,*a:chosen.append(p['name']) or Outcome('success','done'))
        self.assertEqual(chosen,['b'])
        self.assertEqual(self.store.job(job['id'])['status'],'succeeded')
        self.assertEqual(self.store.job(job['id'])['attempts'],1)

    def test_full_week_is_skipped_even_with_free_five_hour_balance(self):
        self.windows('a',five=0,week=100);self.windows('b')
        job=self.submit();chosen=[]
        self.run_tick(lambda p,*a:chosen.append(p['name']) or Outcome('success','done'))
        self.assertEqual(chosen,['b'])
        self.assertEqual(self.store.job(job['id'])['chosen_profile'],'b')

    def test_runtime_quota_keeps_same_job_and_uses_another_profile_next_tick(self):
        self.windows('a',week_reset=300);self.windows('b',week_reset=600)
        job=self.submit();chosen=[]
        def runner(profile,*args):
            chosen.append(profile['name'])
            return Outcome('quota',error='usage_limit_reached') if profile['name']=='a' else Outcome('success','done')
        def unavailable(*args):raise ValueError('No reset observation')
        self.run_tick(runner,probe=unavailable)
        self.assertEqual(self.store.job(job['id'])['status'],'waiting')
        self.assertEqual(self.store.profile('a')['hold_reason'],'quota_reset_unknown')
        self.run_tick(runner,probe=unavailable)
        self.assertEqual(chosen,['a','b'])
        self.assertEqual(self.store.job(job['id'])['status'],'succeeded')
        self.assertEqual(self.store.job(job['id'])['attempts'],2)
        self.assertEqual(len(self.store.jobs()),1)

    def test_waits_for_earliest_profile_that_clears_all_its_windows(self):
        self.windows('a',five=100,week=100,five_reset=10,week_reset=100)
        self.windows('b',five=100,five_reset=20)
        job=self.submit();chosen=[]
        runner=lambda p,*a:chosen.append(p['name']) or Outcome('success','done')
        self.assertFalse(self.run_tick(runner))
        self.assertFalse(self.run_tick(runner,now=self.now+11))
        self.assertEqual(chosen,[])
        self.assertEqual(self.store.job(job['id'])['attempts'],0)
        self.run_tick(runner,now=self.now+21)
        self.assertEqual(chosen,['b'])
        self.assertEqual(self.store.job(job['id'])['status'],'succeeded')

    def test_waiting_codex_job_does_not_block_independent_claude_job(self):
        self.windows('a',five=100);self.windows('b',five=100)
        first=self.submit()
        self.store.add_profile('claude','claude','claude');self.store.update_profile('claude',enabled=True)
        second=self.store.submit('Independent read',self.root,'claude',key='second-job')
        chosen=[];self.run_tick(lambda p,*a:chosen.append(p['name']) or Outcome('success','done'))
        self.assertEqual(chosen,['claude'])
        self.assertEqual(self.store.job(first['id'])['status'],'waiting')
        self.assertEqual(self.store.job(first['id'])['attempts'],0)
        self.assertEqual(self.store.job(second['id'])['status'],'succeeded')

    def test_explicit_pin_to_full_profile_waits_despite_other_free_account(self):
        self.windows('a',five=100);self.windows('b')
        job=self.submit(profile='a');chosen=[]
        self.assertFalse(self.run_tick(lambda p,*a:chosen.append(p['name']) or Outcome('success','unexpected')))
        self.assertEqual(chosen,[])
        self.assertEqual(self.store.job(job['id'])['status'],'waiting')
        self.assertEqual(self.store.job(job['id'])['attempts'],0)

    def test_model_specific_limit_blocks_only_requested_family_without_provider_change(self):
        self.store.add_profile('claude','claude','claude');self.store.update_profile('claude',enabled=True)
        self.store.set_windows('claude',[
            {'key':'five_hour','bucket':'claude','minutes':300,'used':10,'reset':self.now+300},
            {'key':'seven_day_opus','bucket':'claude','minutes':10080,'used':100,'reset':self.now+600,'model':'opus'}])
        sonnet=self.store.submit('Read',self.root,'claude',model='sonnet',key='sonnet')
        opus=self.store.submit('Read',self.root,'claude',model='opus',key='opus')
        chosen=[];runner=lambda p,j,*a:chosen.append((p['name'],j['model'])) or Outcome('success','done')
        self.run_tick(runner);self.run_tick(runner)
        self.assertEqual(chosen,[('claude','sonnet')])
        self.assertEqual(self.store.job(sonnet['id'])['status'],'succeeded')
        self.assertEqual(self.store.job(opus['id'])['status'],'waiting')
        self.assertEqual(self.store.job(opus['id'])['provider'],'claude')
