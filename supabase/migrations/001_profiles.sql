create table public.profiles (
    user_id uuid primary key references auth.users (id) on delete cascade,
    display_name text not null
        check (char_length(btrim(display_name)) between 1 and 40),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

alter table public.profiles enable row level security;

create policy "Users can read their own profile"
    on public.profiles for select
    to authenticated
    using ((select auth.uid()) = user_id);

create policy "Users can create their own profile"
    on public.profiles for insert
    to authenticated
    with check ((select auth.uid()) = user_id);

create policy "Users can update their own profile"
    on public.profiles for update
    to authenticated
    using ((select auth.uid()) = user_id)
    with check ((select auth.uid()) = user_id);

create policy "Users can delete their own profile"
    on public.profiles for delete
    to authenticated
    using ((select auth.uid()) = user_id);

grant select, insert, update, delete on public.profiles to authenticated;

create function public.update_profile_timestamp()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

create trigger profiles_updated_at
    before update on public.profiles
    for each row execute function public.update_profile_timestamp();

create table public.learning_preferences (
    user_id uuid primary key references auth.users (id) on delete cascade,
    goal text not null
        check (char_length(btrim(goal)) between 1 and 80),
    language text not null
        check (char_length(btrim(language)) between 1 and 30),
    reminders_enabled boolean not null default false,
    updated_at timestamptz not null default now()
);

alter table public.learning_preferences enable row level security;

create policy "Users can read their own learning preferences"
    on public.learning_preferences for select
    to authenticated
    using ((select auth.uid()) = user_id);

create policy "Users can create their own learning preferences"
    on public.learning_preferences for insert
    to authenticated
    with check ((select auth.uid()) = user_id);

create policy "Users can update their own learning preferences"
    on public.learning_preferences for update
    to authenticated
    using ((select auth.uid()) = user_id)
    with check ((select auth.uid()) = user_id);

create policy "Users can delete their own learning preferences"
    on public.learning_preferences for delete
    to authenticated
    using ((select auth.uid()) = user_id);

grant select, insert, update, delete on public.learning_preferences to authenticated;

create trigger learning_preferences_updated_at
    before update on public.learning_preferences
    for each row execute function public.update_profile_timestamp();
