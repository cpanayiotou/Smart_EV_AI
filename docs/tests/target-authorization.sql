-- Verified against production migration0018, 2026-11-02. All data rolls back.
-- EXPECTED exception contains ROLLBACK RESULTS. Never use a real owner/connector.
-- 1=granted replay=already_authorized 2=switch_off 3/4=target_capability_stale
-- 5=not_plugged 6=charging_not_false 7=not_off 8=limit_changed 9=state_stale
-- 10/11=plan_changed 12=automation_active 13/14=invalid_params 15=revoked
-- 16=target_capability_stale 17=expired 18=state_stale
DO $$
DECLARE
 o uuid := gen_random_uuid(); cid uuid; iid uuid; rid uuid; req uuid; ver int; g text; res text := '';
 ex timestamptz := date_trunc('milliseconds', now()+interval '50 seconds');
 lpj jsonb := '{"connected":true,"charging":false,"mode":"off","limit_soc":80,"session_kwh":0}';
 p jsonb;
BEGIN
 INSERT INTO public.local_connectors(owner_id,name,token_hash,status,control_enabled,control_capability,control_capability_at,target_capability,target_capability_at,last_seen_at)
 VALUES(o,'rollback-target-test',md5(random()::text),'active',true,'mode-v1',now(),'target-v1',now(),now()) RETURNING id INTO cid;
 INSERT INTO public.integrations(owner_id,provider_id,connector_class,status,config)
 VALUES(o,'evcc','EVCC','healthy',jsonb_build_object('gateway_status','connected','connector_id',cid::text,'live',jsonb_build_object('at',now(),'loadpoints',jsonb_build_array(lpj)))) RETURNING id INTO iid;
 INSERT INTO public.charging_automation(owner_id,enabled,target_soc_pct,departure_local,departure_days,timezone,grid_allowed,charge_power_kw,capacity_kwh,max_session_kwh,max_session_min)
 VALUES(o,false,74,'07:20','{1,2,3,4,5}','Asia/Nicosia',true,11,86.5,32,240);
 SELECT settings_version INTO ver FROM public.charging_automation WHERE owner_id=o;
 FOR n IN 1..18 LOOP
  UPDATE public.local_connectors SET status='active',control_enabled=true,target_capability='target-v1',target_capability_at=now() WHERE id=cid;
  UPDATE public.integrations SET config=jsonb_build_object('gateway_status','connected','connector_id',cid::text,'live',jsonb_build_object('at',now(),'loadpoints',jsonb_build_array(lpj))) WHERE id=iid;
  UPDATE public.automation_runs SET state='cancelled' WHERE owner_id=o;
  p:=jsonb_build_object('loadpoint',1,'target_soc',74,'expected_limit_soc',80,'expires_at',ex);
  CASE n
   WHEN 2 THEN UPDATE public.local_connectors SET control_enabled=false WHERE id=cid;
   WHEN 3 THEN UPDATE public.local_connectors SET target_capability=NULL WHERE id=cid;
   WHEN 4 THEN UPDATE public.local_connectors SET target_capability_at=now()-interval '91 seconds' WHERE id=cid;
   WHEN 5 THEN UPDATE public.integrations SET config=jsonb_set(config,'{live,loadpoints,0,connected}','false') WHERE id=iid;
   WHEN 6 THEN UPDATE public.integrations SET config=jsonb_set(config,'{live,loadpoints,0,charging}','true') WHERE id=iid;
   WHEN 7 THEN UPDATE public.integrations SET config=jsonb_set(config,'{live,loadpoints,0,mode}','"now"') WHERE id=iid;
   WHEN 8 THEN UPDATE public.integrations SET config=jsonb_set(config,'{live,loadpoints,0,limit_soc}','79') WHERE id=iid;
   WHEN 9 THEN UPDATE public.integrations SET config=jsonb_set(config,'{live,at}',to_jsonb(now()-interval '121 seconds')) WHERE id=iid;
   WHEN 10 THEN p:=jsonb_set(p,'{target_soc}','75');
   WHEN 12 THEN
    INSERT INTO public.automation_runs(owner_id,connector_id,loadpoint,window_key,state,departure_at,planned_start_at,energy_kwh,settings_version)
    VALUES(o,cid,1,'target-test','charging',now()+interval '5 hours',now(),20,ver) RETURNING id INTO rid;
   WHEN 13 THEN p:=jsonb_set(p,'{target_soc}','81');
   WHEN 14 THEN p:=p || '{"url":"https://invalid.example"}';
   WHEN 15 THEN UPDATE public.local_connectors SET status='revoked' WHERE id=cid;
   WHEN 16 THEN UPDATE public.local_connectors SET target_capability_at=now()+interval '6 seconds' WHERE id=cid;
   WHEN 17 THEN p:=jsonb_set(p,'{expires_at}',to_jsonb(date_trunc('milliseconds',now()-interval '1 second')));
   WHEN 18 THEN UPDATE public.integrations SET config=jsonb_set(config,'{connector_id}',to_jsonb(gen_random_uuid()::text)) WHERE id=iid;
   ELSE NULL;
  END CASE;
  INSERT INTO public.connector_requests(owner_id,connector_id,command,params,status,origin,created_at,expires_at,plan_version)
  VALUES(o,cid,'evcc.set_target',p,'claimed','manual',now(),CASE WHEN n=17 THEN (p->>'expires_at')::timestamptz ELSE ex END,CASE WHEN n=11 THEN ver+1 ELSE ver END) RETURNING id INTO req;
  g:=public.grant_control(req,cid,o);
  res:=res || n || '=' || g || ' ';
  IF n=1 THEN res:=res || 'replay=' || public.grant_control(req,cid,o) || ' '; END IF;
  UPDATE public.connector_requests SET status='failed',completed_at=now() WHERE id=req;
 END LOOP;
 RAISE EXCEPTION 'ROLLBACK RESULTS: %', res;
END $$;
