const assert = require('node:assert/strict')
const assertEqual = assert.equal
const assertDeepEqual = assert.deepEqual
const model = require('../payload/shell/Commons/NiriModel.js')
let state = model.emptyState()
const send = event => { state = model.reduce(state, event) }
send({WorkspacesChanged:{workspaces:[
  {id:71,idx:1,output:'Virtual-1',is_active:true,is_focused:true},
  {id:90,idx:2,output:'Virtual-1',is_active:false,is_focused:false},
  {id:3,idx:1,output:'DP-2',is_active:true,is_focused:false}
]}})
send({WindowsChanged:{windows:[{id:6,workspace_id:71,is_focused:true},{id:7,workspace_id:3,is_focused:false}]}})
send({WorkspaceActivated:{id:90,focused:true}})
assertEqual(state.workspaces.find(w=>w.id===71).is_active,false,'previous workspace on the same output becomes inactive')
assertEqual(state.workspaces.find(w=>w.id===3).is_active,true,'other output keeps its active workspace')
assertEqual(state.workspaces.filter(w=>w.is_focused).length,1,'only one workspace is focused')
assertDeepEqual(model.workspaceItems(state,'Virtual-1').map(w=>w.id),[71,90],'bar uses stable IDs and filters its output')
assertEqual(model.workspaceItems(state,'Virtual-1')[0].occupied,true,'occupancy is derived from windows')
send({WindowFocusChanged:{id:null}})
assertEqual(state.windows.some(w=>w.is_focused),false,'a focused popup clears application focus')
send({WindowOpenedOrChanged:{window:{id:8,workspace_id:999,is_focused:true}}})
assertEqual(state.windows.some(w=>w.id===8),true,'temporarily unknown workspace does not discard an open window')
send({WindowClosed:{id:6}})
assertEqual(model.workspaceItems(state,'Virtual-1')[0].occupied,false,'closing the final window clears occupancy')
send({KeyboardLayoutsChanged:{keyboard_layouts:{names:['English (US)','German'],current_idx:0}}})
send({KeyboardLayoutSwitched:{idx:1}})
assertEqual(state.keyboard.names[state.keyboard.current_idx],'German','layout events update the visible selection')
const before=state
send({FutureProtocolEvent:{value:1}})
assertEqual(state,before,'unknown events do not destroy current state')
send({WorkspacesChanged:{workspaces:[{id:90,idx:1,output:'DP-2',is_active:true,is_focused:true}]}})
assertDeepEqual(model.workspaceItems(state,'Virtual-1'),[],'reconnection snapshot removes stale workspaces')
console.log('PASS: 11 Niri event model assertions')
