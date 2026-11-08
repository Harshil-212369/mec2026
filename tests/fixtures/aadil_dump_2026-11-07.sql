-- Test fixture: Aadil's Neon database as dumped (pg_dump 18.6) on 2026-11-07 ~14:20 EST.
-- Re-created from the dump pasted in chat (its tabs were lost): world tables rebuilt from
-- data/toronto-downtown.json and checked row-by-row against the starter schema.sql;
-- Aadil's changes applied: app_settings table, tickets without severity, ticket 1 (P3).
-- OWNER/ACL lines removed so it restores into a local Postgres. Replace with a real
-- `pg_dump ... -f` file whenever Aadil's schema changes.
-- Dumped from database version 18.6 (ac70818)
-- Dumped by pg_dump version 18.6

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: datasets; Type: TABLE; Schema: public; Owner: neondb_owner
--

CREATE TABLE public.app_settings (
    setting_id integer DEFAULT 1 NOT NULL,
    active_dataset_id text NOT NULL,
    CONSTRAINT app_settings_setting_id_check CHECK ((setting_id = 1))
);


CREATE TABLE public.datasets (
    dataset_id text NOT NULL,
    name text NOT NULL,
    center_lat double precision,
    center_lng double precision,
    zoom integer
);



--
-- Name: deliveries; Type: TABLE; Schema: public; Owner: neondb_owner
--

CREATE TABLE public.deliveries (
    delivery_id bigint NOT NULL,
    dataset_id text NOT NULL,
    ticket_id bigint NOT NULL,
    supp_id text NOT NULL,
    vehicle_id text NOT NULL,
    servings_assigned integer NOT NULL,
    route jsonb DEFAULT '[]'::jsonb NOT NULL,
    route_weight double precision,
    route_distance_km double precision,
    status text DEFAULT 'Assigned'::text NOT NULL,
    assigned_at timestamp with time zone DEFAULT now() NOT NULL,
    completed_at timestamp with time zone,
    CONSTRAINT deliveries_route_check CHECK ((jsonb_typeof(route) = 'array'::text)),
    CONSTRAINT deliveries_route_distance_km_check CHECK ((route_distance_km >= (0)::double precision)),
    CONSTRAINT deliveries_route_weight_check CHECK ((route_weight >= (0)::double precision)),
    CONSTRAINT deliveries_servings_assigned_check CHECK ((servings_assigned > 0)),
    CONSTRAINT deliveries_status_check CHECK ((status = ANY (ARRAY['Assigned'::text, 'In Progress'::text, 'Delayed'::text, 'Delivered'::text, 'Failed'::text, 'Cancelled'::text])))
);



--
-- Name: deliveries_delivery_id_seq; Type: SEQUENCE; Schema: public; Owner: neondb_owner
--

ALTER TABLE public.deliveries ALTER COLUMN delivery_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.deliveries_delivery_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: nodes; Type: TABLE; Schema: public; Owner: neondb_owner
--

CREATE TABLE public.nodes (
    dataset_id text NOT NULL,
    node_id integer NOT NULL,
    name text NOT NULL,
    lat double precision NOT NULL,
    lng double precision NOT NULL
);



--
-- Name: requesters; Type: TABLE; Schema: public; Owner: neondb_owner
--

CREATE TABLE public.requesters (
    dataset_id text NOT NULL,
    req_id text NOT NULL,
    name text NOT NULL,
    category text NOT NULL,
    location_node integer NOT NULL,
    address text
);



--
-- Name: roads; Type: TABLE; Schema: public; Owner: neondb_owner
--

CREATE TABLE public.roads (
    dataset_id text NOT NULL,
    road_id integer NOT NULL,
    node_a integer NOT NULL,
    node_b integer NOT NULL,
    street text,
    distance_km double precision NOT NULL,
    weight double precision NOT NULL,
    is_highway boolean DEFAULT false NOT NULL,
    terrain text,
    is_closed boolean DEFAULT false NOT NULL,
    CONSTRAINT roads_check CHECK ((node_a <> node_b)),
    CONSTRAINT roads_distance_km_check CHECK ((distance_km >= (0)::double precision)),
    CONSTRAINT roads_weight_check CHECK ((weight >= (0)::double precision))
);



--
-- Name: suppliers; Type: TABLE; Schema: public; Owner: neondb_owner
--

CREATE TABLE public.suppliers (
    dataset_id text NOT NULL,
    supp_id text NOT NULL,
    name text NOT NULL,
    location_node integer NOT NULL,
    address text,
    normal_stock integer DEFAULT 0 NOT NULL,
    cold_stock integer DEFAULT 0 NOT NULL,
    reserved_normal integer DEFAULT 0 NOT NULL,
    reserved_cold integer DEFAULT 0 NOT NULL,
    CONSTRAINT suppliers_check CHECK ((reserved_normal <= normal_stock)),
    CONSTRAINT suppliers_check1 CHECK ((reserved_cold <= cold_stock)),
    CONSTRAINT suppliers_cold_stock_check CHECK ((cold_stock >= 0)),
    CONSTRAINT suppliers_normal_stock_check CHECK ((normal_stock >= 0)),
    CONSTRAINT suppliers_reserved_cold_check CHECK ((reserved_cold >= 0)),
    CONSTRAINT suppliers_reserved_normal_check CHECK ((reserved_normal >= 0))
);



--
-- Name: system_events; Type: TABLE; Schema: public; Owner: neondb_owner
--

CREATE TABLE public.system_events (
    event_id bigint NOT NULL,
    dataset_id text NOT NULL,
    event_type text NOT NULL,
    details jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);



--
-- Name: system_events_event_id_seq; Type: SEQUENCE; Schema: public; Owner: neondb_owner
--

ALTER TABLE public.system_events ALTER COLUMN event_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.system_events_event_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: ticket_history; Type: TABLE; Schema: public; Owner: neondb_owner
--

CREATE TABLE public.ticket_history (
    history_id bigint NOT NULL,
    dataset_id text NOT NULL,
    ticket_id bigint NOT NULL,
    old_status text,
    new_status text NOT NULL,
    reason text NOT NULL,
    changed_at timestamp with time zone DEFAULT now() NOT NULL
);



--
-- Name: ticket_history_history_id_seq; Type: SEQUENCE; Schema: public; Owner: neondb_owner
--

ALTER TABLE public.ticket_history ALTER COLUMN history_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.ticket_history_history_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: tickets; Type: TABLE; Schema: public; Owner: neondb_owner
--

CREATE TABLE public.tickets (
    ticket_id bigint NOT NULL,
    dataset_id text NOT NULL,
    req_id text NOT NULL,
    crisis_type text DEFAULT 'food_shortage'::text NOT NULL,
    servings_requested integer NOT NULL,
    people_affected integer NOT NULL,
    refrigerated boolean DEFAULT false NOT NULL,
    deadline timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    priority_score double precision,
    status text DEFAULT 'Open'::text NOT NULL,
    priority_version integer DEFAULT 0 NOT NULL,
    CONSTRAINT tickets_people_affected_check CHECK ((people_affected > 0)),
    CONSTRAINT tickets_servings_requested_check CHECK ((servings_requested > 0)),
    CONSTRAINT tickets_status_check CHECK ((status = ANY (ARRAY['Open'::text, 'Prioritized'::text, 'Resource Assigned'::text, 'In Progress'::text, 'Re-Routing'::text, 'Delivered'::text, 'Resolved'::text, 'Delayed'::text, 'Failed'::text])))
);



--
-- Name: tickets_ticket_id_seq; Type: SEQUENCE; Schema: public; Owner: neondb_owner
--

ALTER TABLE public.tickets ALTER COLUMN ticket_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.tickets_ticket_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: vehicles; Type: TABLE; Schema: public; Owner: neondb_owner
--

CREATE TABLE public.vehicles (
    dataset_id text NOT NULL,
    vehicle_id text NOT NULL,
    supp_id text NOT NULL,
    name text NOT NULL,
    start_node integer NOT NULL,
    current_node integer NOT NULL,
    capacity integer NOT NULL,
    refrigerated boolean DEFAULT false NOT NULL,
    fuel double precision DEFAULT 100 NOT NULL,
    status text DEFAULT 'Available'::text NOT NULL,
    CONSTRAINT vehicles_capacity_check CHECK ((capacity > 0)),
    CONSTRAINT vehicles_fuel_check CHECK ((fuel >= (0)::double precision)),
    CONSTRAINT vehicles_status_check CHECK ((status = ANY (ARRAY['Available'::text, 'Reserved'::text, 'Delivering'::text, 'Broken'::text, 'Unavailable'::text])))
);



--
-- Data for Name: datasets; Type: TABLE DATA; Schema: public; Owner: neondb_owner
--

COPY public.app_settings (setting_id, active_dataset_id) FROM stdin;
1	toronto-downtown
\.


COPY public.datasets (dataset_id, name, center_lat, center_lng, zoom) FROM stdin;
toronto-downtown	Downtown Toronto	43.657	-79.387	14
\.


--
-- Data for Name: deliveries; Type: TABLE DATA; Schema: public; Owner: neondb_owner
--

COPY public.deliveries (delivery_id, dataset_id, ticket_id, supp_id, vehicle_id, servings_assigned, route, route_weight, route_distance_km, status, assigned_at, completed_at) FROM stdin;
\.


--
-- Data for Name: nodes; Type: TABLE DATA; Schema: public; Owner: neondb_owner
--

COPY public.nodes (dataset_id, node_id, name, lat, lng) FROM stdin;
toronto-downtown	0	Bathurst St & Front St	43.6432	-79.4096
toronto-downtown	1	Spadina Ave & Front St	43.64365	-79.3986
toronto-downtown	2	University Ave & Front St	43.6441	-79.38759999999999
toronto-downtown	3	Bay St & Front St	43.64455	-79.3826
toronto-downtown	4	Yonge St & Front St	43.645	-79.37859999999999
toronto-downtown	5	Church St & Front St	43.645450000000004	-79.3746
toronto-downtown	6	Jarvis St & Front St	43.645900000000005	-79.3706
toronto-downtown	7	Parliament St & Front St	43.646350000000005	-79.36059999999999
toronto-downtown	8	Bathurst St & King St	43.6472	-79.4103
toronto-downtown	9	Spadina Ave & King St	43.64765	-79.39930000000001
toronto-downtown	10	University Ave & King St	43.6481	-79.3883
toronto-downtown	11	Bay St & King St	43.64855	-79.3833
toronto-downtown	12	Yonge St & King St	43.649	-79.3793
toronto-downtown	13	Church St & King St	43.64945	-79.37530000000001
toronto-downtown	14	Jarvis St & King St	43.6499	-79.3713
toronto-downtown	15	Parliament St & King St	43.65035	-79.3613
toronto-downtown	16	Bathurst St & Queen St	43.651199999999996	-79.411
toronto-downtown	17	Spadina Ave & Queen St	43.65165	-79.4
toronto-downtown	18	University Ave & Queen St	43.6521	-79.389
toronto-downtown	19	Bay St & Queen St	43.65255	-79.384
toronto-downtown	20	Yonge St & Queen St	43.653	-79.38
toronto-downtown	21	Church St & Queen St	43.65345	-79.376
toronto-downtown	22	Jarvis St & Queen St	43.6539	-79.372
toronto-downtown	23	Parliament St & Queen St	43.65435	-79.362
toronto-downtown	24	Bathurst St & Dundas St	43.655199999999994	-79.4117
toronto-downtown	25	Spadina Ave & Dundas St	43.655649999999994	-79.4007
toronto-downtown	26	University Ave & Dundas St	43.656099999999995	-79.38969999999999
toronto-downtown	27	Bay St & Dundas St	43.656549999999996	-79.3847
toronto-downtown	28	Yonge St & Dundas St	43.657	-79.38069999999999
toronto-downtown	29	Church St & Dundas St	43.65745	-79.3767
toronto-downtown	30	Jarvis St & Dundas St	43.6579	-79.3727
toronto-downtown	31	Parliament St & Dundas St	43.65835	-79.36269999999999
toronto-downtown	32	Bathurst St & College St	43.6592	-79.4124
toronto-downtown	33	Spadina Ave & College St	43.65965	-79.40140000000001
toronto-downtown	34	University Ave & College St	43.6601	-79.3904
toronto-downtown	35	Bay St & College St	43.66055	-79.3854
toronto-downtown	36	Yonge St & College St	43.661	-79.3814
toronto-downtown	37	Church St & College St	43.66145	-79.37740000000001
toronto-downtown	38	Jarvis St & College St	43.6619	-79.3734
toronto-downtown	39	Parliament St & College St	43.66235	-79.3634
toronto-downtown	40	Bathurst St & Bloor St	43.6682	-79.4131
toronto-downtown	41	Spadina Ave & Bloor St	43.66865	-79.4021
toronto-downtown	42	University Ave & Bloor St	43.6691	-79.3911
toronto-downtown	43	Bay St & Bloor St	43.66955	-79.3861
toronto-downtown	44	Yonge St & Bloor St	43.67	-79.3821
toronto-downtown	45	Church St & Bloor St	43.67045	-79.3781
toronto-downtown	46	Jarvis St & Bloor St	43.6709	-79.3741
toronto-downtown	47	Parliament St & Bloor St	43.671350000000004	-79.3641
\.


--
-- Data for Name: requesters; Type: TABLE DATA; Schema: public; Owner: neondb_owner
--

COPY public.requesters (dataset_id, req_id, name, category, location_node, address) FROM stdin;
toronto-downtown	P3	Toronto General Hospital (approximate)	hospital	34	University Ave
toronto-downtown	P4	Moss Park delivery site (scenario)	shelter	22	Queen St & Jarvis St
toronto-downtown	P5	Waterfront delivery site (scenario)	community	4	Front St & Yonge St
toronto-downtown	P6	Bloor community delivery (scenario)	community	44	Bloor St & Yonge St
\.


--
-- Data for Name: roads; Type: TABLE DATA; Schema: public; Owner: neondb_owner
--

COPY public.roads (dataset_id, road_id, node_a, node_b, street, distance_km, weight, is_highway, terrain, is_closed) FROM stdin;
toronto-downtown	0	0	1	Front St	0.885	2.4136	f	urban	f
toronto-downtown	1	0	8	Bathurst St	0.4475	1.0741	f	urban	f
toronto-downtown	2	1	2	Front St	0.885	2.4136	f	urban	f
toronto-downtown	3	1	9	Spadina Ave	0.4475	1.0741	f	urban	f
toronto-downtown	4	2	3	Front St	0.4047	1.1038	f	urban	f
toronto-downtown	5	2	10	University Ave	0.4475	1.0741	f	urban	f
toronto-downtown	6	3	4	Front St	0.3252	0.8868	f	urban	f
toronto-downtown	7	3	11	Bay St	0.4475	1.0741	f	urban	f
toronto-downtown	8	4	5	Front St	0.3252	0.8868	f	urban	f
toronto-downtown	9	4	12	Yonge St	0.4475	1.0741	f	urban	f
toronto-downtown	10	5	6	Front St	0.3251	0.8868	f	urban	f
toronto-downtown	11	5	13	Church St	0.4475	1.0741	f	urban	f
toronto-downtown	12	6	7	Front St	0.8048	2.1948	f	urban	f
toronto-downtown	13	6	14	Jarvis St	0.4475	1.0741	f	urban	f
toronto-downtown	14	7	15	Parliament St	0.4475	1.0741	f	urban	f
toronto-downtown	15	8	9	King St	0.8849	2.4134	f	urban	f
toronto-downtown	16	8	16	Bathurst St	0.4475	1.0741	f	urban	f
toronto-downtown	17	9	10	King St	0.8849	2.4134	f	urban	f
toronto-downtown	18	9	17	Spadina Ave	0.4475	1.0741	f	urban	f
toronto-downtown	19	10	11	King St	0.4047	1.1037	f	urban	f
toronto-downtown	20	10	18	University Ave	0.4475	1.0741	f	urban	f
toronto-downtown	21	11	12	King St	0.3251	0.8867	f	urban	f
toronto-downtown	22	11	19	Bay St	0.4475	1.0741	f	urban	f
toronto-downtown	23	12	13	King St	0.3251	0.8867	f	urban	f
toronto-downtown	24	12	20	Yonge St	0.4475	1.0741	f	urban	f
toronto-downtown	25	13	14	King St	0.3251	0.8867	f	urban	f
toronto-downtown	26	13	21	Church St	0.4475	1.0741	f	urban	f
toronto-downtown	27	14	15	King St	0.8047	2.1947	f	urban	f
toronto-downtown	28	14	22	Jarvis St	0.4475	1.0741	f	urban	f
toronto-downtown	29	15	23	Parliament St	0.4475	1.0741	f	urban	f
toronto-downtown	30	16	17	Queen St	0.8849	2.4133	f	urban	f
toronto-downtown	31	16	24	Bathurst St	0.4475	1.0741	f	urban	f
toronto-downtown	32	17	18	Queen St	0.8849	2.4133	f	urban	f
toronto-downtown	33	17	25	Spadina Ave	0.4475	1.0741	f	urban	f
toronto-downtown	34	18	19	Queen St	0.4047	1.1036	f	urban	f
toronto-downtown	35	18	26	University Ave	0.4475	1.0741	f	urban	f
toronto-downtown	36	19	20	Queen St	0.3251	0.8867	f	urban	f
toronto-downtown	37	19	27	Bay St	0.4475	1.0741	f	urban	f
toronto-downtown	38	20	21	Queen St	0.3251	0.8867	f	urban	f
toronto-downtown	39	20	28	Yonge St	0.4475	1.0741	f	urban	f
toronto-downtown	40	21	22	Queen St	0.3251	0.8867	f	urban	f
toronto-downtown	41	21	29	Church St	0.4475	1.0741	f	urban	f
toronto-downtown	42	22	23	Queen St	0.8047	2.1945	f	urban	f
toronto-downtown	43	22	30	Jarvis St	0.4475	1.0741	f	urban	f
toronto-downtown	44	23	31	Parliament St	0.4475	1.0741	f	urban	f
toronto-downtown	45	24	25	Dundas St	0.8848	2.4131	f	urban	f
toronto-downtown	46	24	32	Bathurst St	0.4475	1.0741	f	urban	f
toronto-downtown	47	25	26	Dundas St	0.8848	2.4131	f	urban	f
toronto-downtown	48	25	33	Spadina Ave	0.4475	1.0741	f	urban	f
toronto-downtown	49	26	27	Dundas St	0.4046	1.1036	f	urban	f
toronto-downtown	50	26	34	University Ave	0.4475	1.0741	f	urban	f
toronto-downtown	51	27	28	Dundas St	0.3251	0.8866	f	urban	f
toronto-downtown	52	27	35	Bay St	0.4475	1.0741	f	urban	f
toronto-downtown	53	28	29	Dundas St	0.3251	0.8866	f	urban	f
toronto-downtown	54	28	36	Yonge St	0.4475	1.0741	f	urban	f
toronto-downtown	55	29	30	Dundas St	0.3251	0.8866	f	urban	f
toronto-downtown	56	29	37	Church St	0.4475	1.0741	f	urban	f
toronto-downtown	57	30	31	Dundas St	0.8046	2.1944	f	urban	f
toronto-downtown	58	30	38	Jarvis St	0.4475	1.0741	f	urban	f
toronto-downtown	59	31	39	Parliament St	0.4475	1.0741	f	urban	f
toronto-downtown	60	32	33	College St	0.8848	2.413	f	urban	f
toronto-downtown	61	32	40	Bathurst St	1.0006	2.4014	f	urban	f
toronto-downtown	62	33	34	College St	0.8847	2.4129	f	urban	f
toronto-downtown	63	33	41	Spadina Ave	1.0006	2.4014	f	urban	f
toronto-downtown	64	34	35	College St	0.4046	1.1035	f	urban	f
toronto-downtown	65	34	42	University Ave	1.0006	2.4014	f	urban	f
toronto-downtown	66	35	36	College St	0.3251	0.8866	f	urban	f
toronto-downtown	67	35	43	Bay St	1.0006	2.4014	f	urban	f
toronto-downtown	68	36	37	College St	0.3251	0.8865	f	urban	f
toronto-downtown	69	36	44	Yonge St	1.0006	2.4014	f	urban	f
toronto-downtown	70	37	38	College St	0.3251	0.8865	f	urban	f
toronto-downtown	71	37	45	Church St	1.0006	2.4014	f	urban	f
toronto-downtown	72	38	39	College St	0.8046	2.1942	f	urban	f
toronto-downtown	73	38	46	Jarvis St	1.0006	2.4014	f	urban	f
toronto-downtown	74	39	47	Parliament St	1.0006	2.4014	f	urban	f
toronto-downtown	75	40	41	Bloor St	0.8846	2.4126	f	urban	f
toronto-downtown	76	41	42	Bloor St	0.8846	2.4126	f	urban	f
toronto-downtown	77	42	43	Bloor St	0.4045	1.1033	f	urban	f
toronto-downtown	78	43	44	Bloor St	0.325	0.8864	f	urban	f
toronto-downtown	79	44	45	Bloor St	0.325	0.8864	f	urban	f
toronto-downtown	80	45	46	Bloor St	0.325	0.8864	f	urban	f
toronto-downtown	81	46	47	Bloor St	0.8044	2.1939	f	urban	f
\.


--
-- Data for Name: suppliers; Type: TABLE DATA; Schema: public; Owner: neondb_owner
--

COPY public.suppliers (dataset_id, supp_id, name, location_node, address, normal_stock, cold_stock, reserved_normal, reserved_cold) FROM stdin;
toronto-downtown	P0	Fort York Food Bank (approximate)	33	380 College St	300	100	0	0
toronto-downtown	P1	Downtown West supply depot (scenario)	8	King St & Bathurst St	300	100	0	0
toronto-downtown	P2	Downtown East supply depot (scenario)	23	Queen St & Parliament St	300	100	0	0
\.


--
-- Data for Name: system_events; Type: TABLE DATA; Schema: public; Owner: neondb_owner
--

COPY public.system_events (event_id, dataset_id, event_type, details, created_at) FROM stdin;
1	toronto-downtown	crisis-created	{"req_id": "P3", "ticket_id": 1}	2026-11-07 19:20:47.473824+00
\.


--
-- Data for Name: ticket_history; Type: TABLE DATA; Schema: public; Owner: neondb_owner
--

COPY public.ticket_history (history_id, dataset_id, ticket_id, old_status, new_status, reason, changed_at) FROM stdin;
1	toronto-downtown	1	\N	Open	Emergency ticket submitted	2026-11-07 19:20:47.473824+00
\.


--
-- Data for Name: tickets; Type: TABLE DATA; Schema: public; Owner: neondb_owner
--

COPY public.tickets (ticket_id, dataset_id, req_id, crisis_type, servings_requested, people_affected, refrigerated, deadline, created_at, priority_score, status, priority_version) FROM stdin;
1	toronto-downtown	P3	food_shortage	28	70	f	2026-11-07 21:16:00+00	2026-11-07 19:20:47.473824+00	0	Open	0
\.


--
-- Data for Name: vehicles; Type: TABLE DATA; Schema: public; Owner: neondb_owner
--

COPY public.vehicles (dataset_id, vehicle_id, supp_id, name, start_node, current_node, capacity, refrigerated, fuel, status) FROM stdin;
toronto-downtown	V1	P0	Reefer 1	33	33	40	t	100	Available
toronto-downtown	V2	P0	Truck 2	33	33	60	f	100	Available
toronto-downtown	V3	P0	Truck 3	33	33	60	f	100	Available
toronto-downtown	V4	P0	Truck 4	33	33	60	f	100	Available
toronto-downtown	V5	P1	Reefer 5	8	8	40	t	100	Available
toronto-downtown	V6	P1	Truck 6	8	8	60	f	100	Available
toronto-downtown	V7	P1	Truck 7	8	8	60	f	100	Available
toronto-downtown	V8	P1	Truck 8	8	8	60	f	100	Available
toronto-downtown	V9	P2	Reefer 9	23	23	40	t	100	Available
toronto-downtown	V10	P2	Truck 10	23	23	60	f	100	Available
toronto-downtown	V11	P2	Truck 11	23	23	60	f	100	Available
toronto-downtown	V12	P2	Truck 12	23	23	60	f	100	Available
\.


--
-- Name: deliveries_delivery_id_seq; Type: SEQUENCE SET; Schema: public; Owner: neondb_owner
--

SELECT pg_catalog.setval('public.deliveries_delivery_id_seq', 1, false);


--
-- Name: system_events_event_id_seq; Type: SEQUENCE SET; Schema: public; Owner: neondb_owner
--

SELECT pg_catalog.setval('public.system_events_event_id_seq', 1, true);


--
-- Name: ticket_history_history_id_seq; Type: SEQUENCE SET; Schema: public; Owner: neondb_owner
--

SELECT pg_catalog.setval('public.ticket_history_history_id_seq', 1, true);


--
-- Name: tickets_ticket_id_seq; Type: SEQUENCE SET; Schema: public; Owner: neondb_owner
--

SELECT pg_catalog.setval('public.tickets_ticket_id_seq', 1, true);


--
-- Name: datasets datasets_pkey; Type: CONSTRAINT; Schema: public; Owner: neondb_owner
--

ALTER TABLE ONLY public.app_settings
    ADD CONSTRAINT app_settings_pkey PRIMARY KEY (setting_id);


ALTER TABLE ONLY public.datasets
    ADD CONSTRAINT datasets_pkey PRIMARY KEY (dataset_id);


--
-- Name: deliveries deliveries_dataset_id_delivery_id_key; Type: CONSTRAINT; Schema: public; Owner: neondb_owner
--

ALTER TABLE ONLY public.deliveries
    ADD CONSTRAINT deliveries_dataset_id_delivery_id_key UNIQUE (dataset_id, delivery_id);


--
-- Name: deliveries deliveries_pkey; Type: CONSTRAINT; Schema: public; Owner: neondb_owner
--

ALTER TABLE ONLY public.deliveries
    ADD CONSTRAINT deliveries_pkey PRIMARY KEY (delivery_id);


--
-- Name: nodes nodes_pkey; Type: CONSTRAINT; Schema: public; Owner: neondb_owner
--

ALTER TABLE ONLY public.nodes
    ADD CONSTRAINT nodes_pkey PRIMARY KEY (dataset_id, node_id);


--
-- Name: requesters requesters_pkey; Type: CONSTRAINT; Schema: public; Owner: neondb_owner
--

ALTER TABLE ONLY public.requesters
    ADD CONSTRAINT requesters_pkey PRIMARY KEY (dataset_id, req_id);


--
-- Name: roads roads_pkey; Type: CONSTRAINT; Schema: public; Owner: neondb_owner
--

ALTER TABLE ONLY public.roads
    ADD CONSTRAINT roads_pkey PRIMARY KEY (dataset_id, road_id);


--
-- Name: suppliers suppliers_pkey; Type: CONSTRAINT; Schema: public; Owner: neondb_owner
--

ALTER TABLE ONLY public.suppliers
    ADD CONSTRAINT suppliers_pkey PRIMARY KEY (dataset_id, supp_id);


--
-- Name: system_events system_events_pkey; Type: CONSTRAINT; Schema: public; Owner: neondb_owner
--

ALTER TABLE ONLY public.system_events
    ADD CONSTRAINT system_events_pkey PRIMARY KEY (event_id);


--
-- Name: ticket_history ticket_history_pkey; Type: CONSTRAINT; Schema: public; Owner: neondb_owner
--

ALTER TABLE ONLY public.ticket_history
    ADD CONSTRAINT ticket_history_pkey PRIMARY KEY (history_id);


--
-- Name: tickets tickets_dataset_id_ticket_id_key; Type: CONSTRAINT; Schema: public; Owner: neondb_owner
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT tickets_dataset_id_ticket_id_key UNIQUE (dataset_id, ticket_id);


--
-- Name: tickets tickets_pkey; Type: CONSTRAINT; Schema: public; Owner: neondb_owner
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT tickets_pkey PRIMARY KEY (ticket_id);


--
-- Name: vehicles vehicles_pkey; Type: CONSTRAINT; Schema: public; Owner: neondb_owner
--

ALTER TABLE ONLY public.vehicles
    ADD CONSTRAINT vehicles_pkey PRIMARY KEY (dataset_id, vehicle_id);


--
-- Name: deliveries deliveries_dataset_id_supp_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: neondb_owner
--

ALTER TABLE ONLY public.app_settings
    ADD CONSTRAINT app_settings_active_dataset_id_fkey FOREIGN KEY (active_dataset_id) REFERENCES public.datasets(dataset_id);


ALTER TABLE ONLY public.deliveries
    ADD CONSTRAINT deliveries_dataset_id_supp_id_fkey FOREIGN KEY (dataset_id, supp_id) REFERENCES public.suppliers(dataset_id, supp_id);


--
-- Name: deliveries deliveries_dataset_id_ticket_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: neondb_owner
--

ALTER TABLE ONLY public.deliveries
    ADD CONSTRAINT deliveries_dataset_id_ticket_id_fkey FOREIGN KEY (dataset_id, ticket_id) REFERENCES public.tickets(dataset_id, ticket_id);


--
-- Name: deliveries deliveries_dataset_id_vehicle_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: neondb_owner
--

ALTER TABLE ONLY public.deliveries
    ADD CONSTRAINT deliveries_dataset_id_vehicle_id_fkey FOREIGN KEY (dataset_id, vehicle_id) REFERENCES public.vehicles(dataset_id, vehicle_id);


--
-- Name: nodes nodes_dataset_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: neondb_owner
--

ALTER TABLE ONLY public.nodes
    ADD CONSTRAINT nodes_dataset_id_fkey FOREIGN KEY (dataset_id) REFERENCES public.datasets(dataset_id);


--
-- Name: requesters requesters_dataset_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: neondb_owner
--

ALTER TABLE ONLY public.requesters
    ADD CONSTRAINT requesters_dataset_id_fkey FOREIGN KEY (dataset_id) REFERENCES public.datasets(dataset_id);


--
-- Name: requesters requesters_dataset_id_location_node_fkey; Type: FK CONSTRAINT; Schema: public; Owner: neondb_owner
--

ALTER TABLE ONLY public.requesters
    ADD CONSTRAINT requesters_dataset_id_location_node_fkey FOREIGN KEY (dataset_id, location_node) REFERENCES public.nodes(dataset_id, node_id);


--
-- Name: roads roads_dataset_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: neondb_owner
--

ALTER TABLE ONLY public.roads
    ADD CONSTRAINT roads_dataset_id_fkey FOREIGN KEY (dataset_id) REFERENCES public.datasets(dataset_id);


--
-- Name: roads roads_dataset_id_node_a_fkey; Type: FK CONSTRAINT; Schema: public; Owner: neondb_owner
--

ALTER TABLE ONLY public.roads
    ADD CONSTRAINT roads_dataset_id_node_a_fkey FOREIGN KEY (dataset_id, node_a) REFERENCES public.nodes(dataset_id, node_id);


--
-- Name: roads roads_dataset_id_node_b_fkey; Type: FK CONSTRAINT; Schema: public; Owner: neondb_owner
--

ALTER TABLE ONLY public.roads
    ADD CONSTRAINT roads_dataset_id_node_b_fkey FOREIGN KEY (dataset_id, node_b) REFERENCES public.nodes(dataset_id, node_id);


--
-- Name: suppliers suppliers_dataset_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: neondb_owner
--

ALTER TABLE ONLY public.suppliers
    ADD CONSTRAINT suppliers_dataset_id_fkey FOREIGN KEY (dataset_id) REFERENCES public.datasets(dataset_id);


--
-- Name: suppliers suppliers_dataset_id_location_node_fkey; Type: FK CONSTRAINT; Schema: public; Owner: neondb_owner
--

ALTER TABLE ONLY public.suppliers
    ADD CONSTRAINT suppliers_dataset_id_location_node_fkey FOREIGN KEY (dataset_id, location_node) REFERENCES public.nodes(dataset_id, node_id);


--
-- Name: system_events system_events_dataset_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: neondb_owner
--

ALTER TABLE ONLY public.system_events
    ADD CONSTRAINT system_events_dataset_id_fkey FOREIGN KEY (dataset_id) REFERENCES public.datasets(dataset_id);


--
-- Name: ticket_history ticket_history_dataset_id_ticket_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: neondb_owner
--

ALTER TABLE ONLY public.ticket_history
    ADD CONSTRAINT ticket_history_dataset_id_ticket_id_fkey FOREIGN KEY (dataset_id, ticket_id) REFERENCES public.tickets(dataset_id, ticket_id);


--
-- Name: tickets tickets_dataset_id_req_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: neondb_owner
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT tickets_dataset_id_req_id_fkey FOREIGN KEY (dataset_id, req_id) REFERENCES public.requesters(dataset_id, req_id);


--
-- Name: vehicles vehicles_dataset_id_current_node_fkey; Type: FK CONSTRAINT; Schema: public; Owner: neondb_owner
--

ALTER TABLE ONLY public.vehicles
    ADD CONSTRAINT vehicles_dataset_id_current_node_fkey FOREIGN KEY (dataset_id, current_node) REFERENCES public.nodes(dataset_id, node_id);


--
-- Name: vehicles vehicles_dataset_id_start_node_fkey; Type: FK CONSTRAINT; Schema: public; Owner: neondb_owner
--

ALTER TABLE ONLY public.vehicles
    ADD CONSTRAINT vehicles_dataset_id_start_node_fkey FOREIGN KEY (dataset_id, start_node) REFERENCES public.nodes(dataset_id, node_id);


--
-- Name: vehicles vehicles_dataset_id_supp_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: neondb_owner
--

ALTER TABLE ONLY public.vehicles
    ADD CONSTRAINT vehicles_dataset_id_supp_id_fkey FOREIGN KEY (dataset_id, supp_id) REFERENCES public.suppliers(dataset_id, supp_id);


--
--



--
--



--
-- PostgreSQL database dump complete
--
