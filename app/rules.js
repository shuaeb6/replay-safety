export const modules = {
 zone: {name:'Walkway watch',icon:'route',description:'Flag time spent outside the designated pedestrian route.',camera:'corridor',unit:'seconds',defaultThreshold:2},
 load: {name:'Load visibility',icon:'layers',description:'Review a tall stack that may obstruct the operator’s view.',camera:'loading',unit:'seconds',defaultThreshold:1},
 panel: {name:'Panel watch',icon:'shield',description:'Flag a panel left visibly open.',camera:'machine',unit:'seconds',defaultThreshold:2}
};
export const cameras = [
 {id:'corridor',name:'Production walkway',location:'Factory · Camera 01',file:'0_te21',reference:'4_te5',module:'zone',duration:10.477582,event:{start:1,end:8,title:'Outside pedestrian route',detail:'Illustrative interval for the source walkway example. Review the video to verify the event.'}},
 {id:'loading',name:'Material handling',location:'Factory · Camera 02',file:'3_te7',reference:'7_te3',module:'load',duration:4,event:{start:.2,end:3.7,title:'Tall load · review visibility',detail:'Source example contains a tall stack. This does not establish load weight or a collision risk.'}},
 {id:'machine',name:'Machine floor',location:'Factory · Camera 03',file:'2_te12',reference:'6_te12',module:'panel',duration:10.4,event:{start:.5,end:9,title:'Panel state · review required',detail:'Illustrative interval based on the publisher’s open-panel category. Confirm the specific panel in the footage.'}}
];
export function interpret(text) {
 const t=text.trim().toLowerCase();
 if(!t)return {error:'Describe what you want to watch, or choose an example below.'};
 if(/helmet|hard.?hat|ppe|vest|glove|fire|smoke|speed|block|obstruct.*(route|exit)|theft|steal/.test(t))return {error:'This capability is not connected yet. This demo supports walkway rules, tall-load review, and panel state.'};
 const hits=[];
 if(/walk|zone|restricted|pedestrian|lane|perimeter/.test(t))hits.push('zone');
 if(/forklift|load|stack|operator|visibility/.test(t))hits.push('load');
 if(/panel|cabinet|cover/.test(t))hits.push('panel');
 if(hits.length!==1)return {error:hits.length?'Use one requirement at a time so each rule can be reviewed.':'Try “Keep people on the walkway”, “Flag tall forklift loads”, or “Watch for an open panel”.'};
 const match=t.match(/(\d+(?:\.\d+)?)\s*(seconds?|secs?|s)\b/);
 const threshold=match?Number(match[1]):modules[hits[0]].defaultThreshold;
 if(threshold<.1||threshold>60)return {error:'Choose a duration between 0.1 and 60 seconds.'};
 return {module:hits[0],threshold,text:text.trim()};
}
export function evaluate(camera,rule,time,reference=false){
 if(!rule||rule.module!==camera.module||reference)return null;
 const e=camera.event;
 if(e.end-e.start<rule.threshold||time<e.start+rule.threshold||time>e.end)return null;
 return {...e,trigger:e.start+rule.threshold};
}
export function compatible(camera,rule){return camera.module===rule.module;}
