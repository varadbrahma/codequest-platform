create table public.leaderboard_entries (
    user_id uuid primary key references auth.users (id) on delete cascade,
    display_name text not null
        check (char_length(btrim(display_name)) between 1 and 40),
    xp integer not null default 0 check (xp >= 0),
    updated_at timestamptz not null default now()
);

alter table public.leaderboard_entries enable row level security;

create policy "Signed-in users can view leaderboard names and scores"
    on public.leaderboard_entries for select
    to authenticated
    using (true);

revoke all on public.leaderboard_entries from anon, authenticated;
grant select on public.leaderboard_entries to authenticated;
grant all on public.leaderboard_entries to service_role;

create table public.leaderboard_mission_completions (
    user_id uuid not null references auth.users (id) on delete cascade,
    mission_id integer not null check (mission_id between 1 and 15),
    awarded_xp integer not null check (awarded_xp between 1 and 1000),
    completed_at timestamptz not null default now(),
    primary key (user_id, mission_id)
);

alter table public.leaderboard_mission_completions enable row level security;
revoke all on public.leaderboard_mission_completions from anon, authenticated;
grant all on public.leaderboard_mission_completions to service_role;

create trigger leaderboard_entries_updated_at
    before update on public.leaderboard_entries
    for each row execute function public.update_profile_timestamp();

create or replace function public.record_mission_completion(
    p_user_id uuid,
    p_mission_id integer,
    p_awarded_xp integer,
    p_display_name text
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
    inserted_count integer;
begin
    if p_mission_id not between 1 and 15
        or p_awarded_xp not between 1 and 1000
        or char_length(btrim(p_display_name)) not between 1 and 40 then
        raise exception 'Invalid leaderboard completion';
    end if;

    insert into public.leaderboard_mission_completions (user_id, mission_id, awarded_xp)
    values (p_user_id, p_mission_id, p_awarded_xp)
    on conflict (user_id, mission_id) do nothing;

    get diagnostics inserted_count = row_count;

    insert into public.leaderboard_entries (user_id, display_name, xp)
    values (
        p_user_id,
        btrim(p_display_name),
        case when inserted_count > 0 then p_awarded_xp else 0 end
    )
    on conflict (user_id) do update
    set display_name = excluded.display_name,
        xp = public.leaderboard_entries.xp + excluded.xp;

    return inserted_count > 0;
end;
$$;

create or replace function public.get_codequest_leaderboard(p_user_id uuid)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
    with ranked as (
        select
            user_id,
            display_name,
            xp,
            row_number() over (order by xp desc, updated_at asc, user_id asc)::integer as rank
        from public.leaderboard_entries
    )
    select jsonb_build_object(
        'entries',
        coalesce(
            (
                select jsonb_agg(
                    jsonb_build_object(
                        'rank', ranked.rank,
                        'display_name', ranked.display_name,
                        'xp', ranked.xp,
                        'is_you', ranked.user_id = p_user_id
                    )
                    order by ranked.rank
                )
                from ranked
                where ranked.rank <= 50
            ),
            '[]'::jsonb
        ),
        'current_user',
        (
            select jsonb_build_object(
                'rank', ranked.rank,
                'display_name', ranked.display_name,
                'xp', ranked.xp
            )
            from ranked
            where ranked.user_id = p_user_id
        )
    );
$$;

revoke all on function public.record_mission_completion(uuid, integer, integer, text)
    from public, anon, authenticated;
grant execute on function public.record_mission_completion(uuid, integer, integer, text)
    to service_role;

revoke all on function public.get_codequest_leaderboard(uuid)
    from public, anon, authenticated;
grant execute on function public.get_codequest_leaderboard(uuid)
    to service_role;
