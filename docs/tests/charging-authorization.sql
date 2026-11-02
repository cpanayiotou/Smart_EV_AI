-- Validated 2026-11-02 against cloud migration0017. Cases15/16/17 grant14h/23h59m/exact24h.
-- Cases18/19/20/21 rejectfuturemeasurement/stalereceipt/revokedconnector/stalefetch.
-- EXPECTED EXCEPTION: RESULTS is raised deliberately to roll back ALL synthetic rows.
-- No request can reach a real connector: the test uses a random owner and connector, within one transaction.
-- Exercises the PRODUCTION public.grant_control / fresh_abrp_soc against synthetic rows for a random owner,
-- then raises to roll everything back (nothing persists, no connector ever sees these requests).
-- Run via the database SQL tool; the raised message lists "case=result" pairs.
-- Expected (verified 2 Nov 2026): 1=granted 2=soc_not_fresh 3=soc_not_fresh 4=charging_not_false 5=native_limit_missing
-- 6=energy_baseline 7=not_off 8=soc_not_fresh 9=granted 10=granted 11=automation_run 12=invalid_params 13=energy_budget_used 14=max_duration
DO $$
DECLARE
  o uuid := gen_random_uuid(); cid uuid; iid uuid; rid uuid; req uuid; v int; res text := '';
  dep timestamptz := date_trunc('milliseconds', now() + interval '5 hours');
  ex timestamptz := date_trunc('milliseconds', now() + interval '50 seconds');
  lpj jsonb := '{"connected":true,"charging":false,"mode":"off","session_kwh":3.2,"limit_soc":80,"limit_energy_kwh":null,"power_w":0}';
  snap jsonb;
  g text;
BEGIN
  INSERT INTO public.local_connectors (owner_id, name, token_hash, status, control_enabled, control_enabled_at, control_capability, control_capability_at, automation_capability, automation_capability_at, last_seen_at)
    VALUES (o, 'test', md5(random()::text), 'active', true, now(), 'mode-v1', now(), 'lease-v1', now(), now()) RETURNING id INTO cid;
  INSERT INTO public.integrations (owner_id, provider_id, connector_class, status, config)
    VALUES (o, 'evcc', 'EVCC', 'healthy', jsonb_build_object('gateway_status','connected','connector_id',cid::text,'live',jsonb_build_object('at',now(),'loadpoints',jsonb_build_array(lpj)))) RETURNING id INTO iid;
  INSERT INTO public.charging_automation (owner_id, enabled, target_soc_pct, departure_local, departure_days, timezone, grid_allowed, charge_power_kw, capacity_kwh, max_session_kwh, max_session_min)
    VALUES (o, true, 70, '07:20', '{1,2,3,4,5}', 'Europe/Nicosia', true, 11, 86.5, 30, 300);
  SELECT settings_version INTO v FROM public.charging_automation WHERE owner_id = o;
  UPDATE public.charging_automation SET consent_version = settings_version WHERE owner_id = o;
  SELECT settings_version INTO v FROM public.charging_automation WHERE owner_id = o;
  UPDATE public.charging_automation SET consent_version = v WHERE owner_id = o;
  snap := jsonb_build_object('vehicle_id', 732885632742, 'fields', jsonb_build_object('soc', jsonb_build_object('provider','enode','available',true,'value',44,'last_known_value',44,'timestamp',extract(epoch FROM now()) - 60,'max_age_seconds',86400,'unit','%')));
  INSERT INTO public.vehicle_telemetry (owner_id, connector_id, vehicle_id, fetched_at, received_at, snapshot) VALUES (o, cid, 732885632742, now(), now(), snap);
  INSERT INTO public.automation_runs (owner_id, connector_id, loadpoint, window_key, state, departure_at, planned_start_at, energy_kwh, settings_version, start_queued_at, baseline_session_kwh, lease_s)
    VALUES (o, cid, 1, 'test', 'start_requested', dep, now(), 20, v, now(), 3.2, 120) RETURNING id INTO rid;

  -- helper pattern: insert claimed request, bind to run, grant, then close it
  FOR i IN 1..21 LOOP
    UPDATE public.local_connectors SET status='active', revoked_at=NULL, control_enabled=true WHERE id=cid;
    UPDATE public.charging_automation SET paused_until=NULL WHERE owner_id=o;
    -- per-case setup
    UPDATE public.integrations SET config = jsonb_set(config, '{live}', jsonb_build_object('at',now(),'loadpoints',jsonb_build_array(lpj))) WHERE id = iid;
    UPDATE public.vehicle_telemetry SET snapshot = snap, received_at = now(), fetched_at = now(), last_error_at = NULL WHERE owner_id = o;
    UPDATE public.charging_automation SET target_soc_pct = 70 WHERE owner_id = o;
    SELECT settings_version INTO v FROM public.charging_automation WHERE owner_id = o;
    UPDATE public.charging_automation SET consent_version = v WHERE owner_id = o;
    UPDATE public.automation_runs SET state = 'start_requested', settings_version = v, departure_at = dep, start_queued_at = now(), baseline_session_kwh = 3.2 WHERE id = rid;
    CASE i
      WHEN 15 THEN UPDATE public.vehicle_telemetry SET snapshot=jsonb_set(snap,'{fields,soc,timestamp}',to_jsonb(extract(epoch FROM now())-50400)) WHERE owner_id=o;
      WHEN 16 THEN UPDATE public.vehicle_telemetry SET snapshot=jsonb_set(snap,'{fields,soc,timestamp}',to_jsonb(extract(epoch FROM now())-86340)) WHERE owner_id=o;
      WHEN 17 THEN UPDATE public.vehicle_telemetry SET snapshot=jsonb_set(snap,'{fields,soc,timestamp}',to_jsonb(extract(epoch FROM now())-86400)) WHERE owner_id=o;
      WHEN 18 THEN UPDATE public.vehicle_telemetry SET snapshot=jsonb_set(snap,'{fields,soc,timestamp}',to_jsonb(extract(epoch FROM now())+31)) WHERE owner_id=o;
      WHEN 19 THEN UPDATE public.vehicle_telemetry SET received_at=now()-interval '181 seconds' WHERE owner_id=o;
      WHEN 20 THEN UPDATE public.local_connectors SET status='revoked',revoked_at=now() WHERE id=cid;
      WHEN 21 THEN UPDATE public.vehicle_telemetry SET fetched_at=now()-interval '901 seconds' WHERE owner_id=o;
      WHEN 2 THEN UPDATE public.vehicle_telemetry SET snapshot = jsonb_set(snap, '{fields,soc,timestamp}', to_jsonb(extract(epoch FROM now()) - 86401)) WHERE owner_id = o; -- >24 h own measurement age (14 h is eligible)
      WHEN 3 THEN UPDATE public.vehicle_telemetry SET last_error_at = now() WHERE owner_id = o;
      WHEN 4 THEN UPDATE public.integrations SET config = jsonb_set(config, '{live,loadpoints,0,charging}', 'null') WHERE id = iid;
      WHEN 5 THEN UPDATE public.integrations SET config = jsonb_set(jsonb_set(config, '{live,loadpoints,0,limit_soc}', 'null'), '{live,loadpoints,0,limit_energy_kwh}', 'null') WHERE id = iid;
      WHEN 6 THEN UPDATE public.integrations SET config = jsonb_set(config, '{live,loadpoints,0,session_kwh}', '4.0') WHERE id = iid; -- energy moved between queue and grant
      WHEN 7 THEN UPDATE public.integrations SET config = jsonb_set(config, '{live,loadpoints,0,mode}', '"pv"') WHERE id = iid;
      WHEN 8 THEN UPDATE public.vehicle_telemetry SET snapshot = '{"fields":{}}' WHERE owner_id = o; -- only evcc SoC (receipt time) left
      WHEN 13 THEN UPDATE public.integrations SET config = jsonb_set(config, '{live,loadpoints,0,session_kwh}', '23.5') WHERE id = iid;
      ELSE NULL;
    END CASE;
    IF i = 9 THEN
      -- stop at/after departure: original lease and deadline both in the past, live state and SoC stale
      UPDATE public.automation_runs SET state = 'stop_requested', departure_at = date_trunc('milliseconds', now() - interval '1 minute') WHERE id = rid;
      UPDATE public.integrations SET config = jsonb_set(config, '{live,at}', to_jsonb(now() - interval '1 hour')) WHERE id = iid;
      UPDATE public.vehicle_telemetry SET received_at = now() - interval '2 hours' WHERE owner_id = o;
      UPDATE public.local_connectors SET control_enabled = false WHERE id = cid;
    ELSIF i = 10 THEN
      -- pause/disable after lease expiry: stop still allowed
      UPDATE public.automation_runs SET state = 'stop_requested' WHERE id = rid;
      UPDATE public.charging_automation SET paused_until = now() + interval '1 hour' WHERE owner_id = o;
    ELSIF i = 11 OR i = 12 THEN
      UPDATE public.automation_runs SET state = 'stop_requested' WHERE id = rid;
    ELSIF i = 13 OR i = 14 THEN
      UPDATE public.automation_runs SET state = 'charging' WHERE id = rid;
      IF i = 14 THEN UPDATE public.automation_runs SET start_queued_at = now() - interval '301 minutes' WHERE id = rid; END IF;
    ELSE
      UPDATE public.local_connectors SET control_enabled = true WHERE id = cid;
      UPDATE public.charging_automation SET paused_until = NULL WHERE owner_id = o;
    END IF;

    IF i = 11 THEN
      -- unknown run: stop for a run id that does not exist
      req := gen_random_uuid();
      INSERT INTO public.connector_requests (id, owner_id, connector_id, command, params, status, expires_at, origin, automation_run_id, claimed_at)
        VALUES (req, o, cid, 'evcc.automation', jsonb_build_object('loadpoint',1,'action','stop','run_id',req::text,'expires_at',to_char(ex AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'),'lease_until',to_char((now() - interval '10 minutes') AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'),'deadline',to_char(dep AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')), 'claimed', ex, 'automation', req, now());
    ELSE
      req := gen_random_uuid();
      INSERT INTO public.connector_requests (id, owner_id, connector_id, command, params, status, expires_at, origin, automation_run_id, claimed_at)
        SELECT req, o, cid, 'evcc.automation', jsonb_build_object('loadpoint',1,
          'action', CASE WHEN i BETWEEN 9 AND 12 THEN 'stop' WHEN i IN (13,14) THEN 'renew' ELSE 'start' END,
          'run_id', rid::text,
          'expires_at', to_char(ex AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'),
          'lease_until', to_char((CASE WHEN i IN (9,10) THEN LEAST(now() - interval '5 minutes', r.departure_at) ELSE LEAST(now() + interval '110 seconds', r.departure_at) END) AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'),
          'deadline', to_char((CASE WHEN i = 12 THEN r.departure_at + interval '1 hour' ELSE r.departure_at END) AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')),
          'claimed', ex, 'automation', rid, now()
        FROM public.automation_runs r WHERE r.id = rid;
      UPDATE public.automation_runs SET start_request_id = CASE WHEN i <= 8 OR i >= 15 THEN req ELSE start_request_id END,
        stop_request_id = CASE WHEN i BETWEEN 9 AND 12 THEN req ELSE stop_request_id END,
        renew_request_id = CASE WHEN i IN (13,14) THEN req ELSE renew_request_id END WHERE id = rid;
    END IF;
    g := public.grant_control(req, cid, o);
    res := res || i || '=' || g || ' ';
    UPDATE public.connector_requests SET status = 'done', completed_at = now() WHERE id = req;
  END LOOP;
  RAISE EXCEPTION 'RESULTS: %', res;
END $$;

