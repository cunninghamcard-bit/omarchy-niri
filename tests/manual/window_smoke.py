"""Run inside a disposable Niri desktop; opens three temporary foot windows."""
import json,subprocess,time

def run(*args):
  return subprocess.check_output(args,text=True).strip()
def msg(name):
  return json.loads(run('niri','msg','--json',name))
def action(*args):
  return run('niri','msg','action',*args)
def wait_for(test):
  for _ in range(80):
    value=test()
    if value:return value
    time.sleep(.05)
  raise AssertionError('condition did not settle')
def windows():return sorted([w for w in msg('windows') if w['app_id'].startswith('niri-qa-')], key=lambda w:w['app_id'])
try:
  for number in range(3):
    action('spawn','--','foot','--app-id=niri-qa-'+str(number),'--title=Niri QA '+str(number),'sh','-c','printf "Niri scrolling test\\n"; sleep 120')
    wait_for(lambda:len(windows())==number+1)
  ws=windows(); output=msg('focused-output')['logical']
  assert all(w['layout']['window_size'][0] < output['width']*.6 for w in ws)
  action('focus-window','--id',str(ws[0]['id']))
  wait_for(lambda:msg('focused-window')['id']==ws[0]['id'])
  action('center-column')
  action('set-column-width','40%')
  wait_for(lambda:msg('focused-window')['layout']['window_size'][0] < output['width']*.5)
  action('toggle-window-floating')
  wait_for(lambda:msg('focused-window')['is_floating'])
  action('toggle-window-floating')
  wait_for(lambda:not msg('focused-window')['is_floating'])
  action('move-column-to-workspace','2')
  wait_for(lambda:next(w for w in msg('windows') if w['id']==ws[0]['id'])['workspace_id'] != ws[1]['workspace_id'])
  run('omarchy-focus-app','^niri-qa-1$')
  wait_for(lambda:msg('focused-window')['id']==ws[1]['id'])
  print('PASS: half-width empty space, scroll/focus, centering, resize, floating, workspace move, application focus')
  print(json.dumps(msg('windows')))
finally:
  for window in windows():action('close-window','--id',str(window['id']))
