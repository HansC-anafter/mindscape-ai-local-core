import type { DiscoveredAccount } from './types';
import { parseCountTextToNumber } from './utils';

const toTime = (value: any): number => {
  const t = new Date(value || 0).getTime();
  return Number.isFinite(t) ? t : 0;
};

const isTruthyString = (v: any): v is string => typeof v === 'string' && v.trim().length > 0;

const shouldOverwrite = (existingCapturedAt: string | undefined, nextCapturedAt: string | undefined): boolean => {
  return toTime(nextCapturedAt) >= toTime(existingCapturedAt);
};

const buildSourceKey = (source: any): string => {
  const artifactId = source?.artifact_id;
  const capturedAt = source?.captured_at;
  const seedVersion = source?.seed_version;
  return `${artifactId || ''}::${capturedAt || ''}::${seedVersion || ''}`;
};

const mergeSourceEntries = (existing: any[] = [], incoming: any[] = []): any[] => {
  const seen = new Set<string>();
  const out: any[] = [];
  [...existing, ...incoming].forEach((s) => {
    if (!s) return;
    const k = buildSourceKey(s);
    if (seen.has(k)) return;
    seen.add(k);
    out.push(s);
  });
  return out;
};

const mergeSourceEntry = (existing: any[] = [], next: any): any[] => {
  return mergeSourceEntries(existing, next ? [next] : []);
};

const mergeTags = (existing: string[] = [], incoming: string[] = []): string[] => {
  const seen = new Set<string>();
  const out: string[] = [];
  [...existing, ...incoming].forEach((tag) => {
    const normalized = (tag || '').trim();
    if (!normalized) return;
    if (seen.has(normalized)) return;
    seen.add(normalized);
    out.push(normalized);
  });
  return out;
};

const mergeStringField = (
  current: string | undefined,
  next: string | undefined,
  overwrite: boolean
): string | undefined => {
  if (overwrite && isTruthyString(next)) return next;
  return current || (isTruthyString(next) ? next : undefined);
};

const mergeNumberField = (
  current: number | undefined,
  next: number | undefined,
  overwrite: boolean
): number | undefined => {
  if (overwrite && typeof next === 'number') return next;
  return current ?? (typeof next === 'number' ? next : undefined);
};

const mergeBooleanField = (
  current: boolean | undefined,
  next: boolean | undefined,
  overwrite: boolean
): boolean => {
  if (overwrite) return !!next;
  return !!current || !!next;
};

const mergeAccount = (current: DiscoveredAccount, next: DiscoveredAccount): DiscoveredAccount => {
  const overwrite = shouldOverwrite(current.fetched_at, next.fetched_at);
  return {
    ...current,
    account_id: current.account_id || next.account_id,
    handle: current.handle || next.handle,
    source: current.source || next.source,
    sources: mergeSourceEntries(current.sources || [], next.sources || []),
    tags: mergeTags(current.tags || [], next.tags || []),
    fetched_at: overwrite ? next.fetched_at : current.fetched_at,
    name: mergeStringField(current.name, next.name, overwrite),
    bio: mergeStringField(current.bio, next.bio, overwrite),
    profile_picture_url: mergeStringField(current.profile_picture_url, next.profile_picture_url, overwrite),
    external_url: mergeStringField(current.external_url, next.external_url, overwrite),
    follower_count: mergeNumberField(current.follower_count, next.follower_count, overwrite),
    following_count: mergeNumberField(current.following_count, next.following_count, overwrite),
    post_count: mergeNumberField(current.post_count, next.post_count, overwrite),
    category: mergeStringField(current.category, next.category, overwrite),
    is_verified: mergeBooleanField(current.is_verified, next.is_verified, overwrite),
    public_email: mergeStringField(current.public_email, next.public_email, overwrite),
    public_phone_number: mergeStringField(current.public_phone_number, next.public_phone_number, overwrite),
    business_address_json: mergeStringField(current.business_address_json, next.business_address_json, overwrite),
  };
};

export function mergeDiscoveredAccounts(
  existing: DiscoveredAccount[],
  incoming: DiscoveredAccount[],
  options?: { prependNew?: boolean }
): DiscoveredAccount[] {
  const prependNew = options?.prependNew === true;
  const byHandle = new Map<string, DiscoveredAccount>();
  const order: string[] = [];

  existing.forEach((account) => {
    byHandle.set(account.handle, {
      ...account,
      sources: account.sources ? [...account.sources] : [],
      tags: account.tags ? [...account.tags] : [],
    });
    order.push(account.handle);
  });

  const newHandles: string[] = [];
  incoming.forEach((account) => {
    const handle = account.handle;
    if (!handle) return;
    const current = byHandle.get(handle);
    if (!current) {
      byHandle.set(handle, {
        ...account,
        sources: account.sources ? [...account.sources] : [],
        tags: account.tags ? [...account.tags] : [],
      });
      newHandles.push(handle);
      return;
    }
    byHandle.set(handle, mergeAccount(current, account));
  });

  const mergedOrder = prependNew ? [...newHandles, ...order] : [...order, ...newHandles];
  const seen = new Set<string>();
  return mergedOrder
    .filter((handle) => {
      if (!handle || seen.has(handle)) return false;
      seen.add(handle);
      return true;
    })
    .map((handle) => byHandle.get(handle))
    .filter((account): account is DiscoveredAccount => !!account);
}

export function buildDiscoveredAccountsFromArtifactsResponse(data: any): DiscoveredAccount[] {
  const byHandle = new Map<string, DiscoveredAccount>();

  (data?.artifacts || []).forEach((artifact: any) => {
    const metadata = artifact.metadata || {};
    const content = artifact.content?.content || artifact.content || {};

    if (
      metadata.source === 'ig_analyze_following' ||
      metadata.source === 'ig_analyze_following_progress' ||
      content.discovered_accounts
    ) {
      const discoveredAccounts = content.discovered_accounts || content.accounts || [];
      discoveredAccounts.forEach((account: any, index: number) => {
        const handle = account.handle || account.username || '';
        if (!handle) return;

        const stableId =
          account.account_id ||
          (handle ? `${artifact.id || artifact.artifact_id}_${handle}` : undefined) ||
          `${artifact.id || artifact.artifact_id}_${index}`;

        const externalUrl =
          account.external_url ||
          account.website_url ||
          undefined;

        const followerCount =
          account.follower_count ??
          account.followers ??
          parseCountTextToNumber(account.follower_count_text);

        const followingCount =
          account.following_count ??
          account.following ??
          parseCountTextToNumber(account.following_count_text);

        const postCount =
          account.post_count ??
          account.posts ??
          parseCountTextToNumber(account.post_count_text);

        const capturedAt =
          account.fetched_at ||
          metadata.captured_at ||
          artifact.updated_at ||
          artifact.created_at ||
          new Date().toISOString();

        const targetSeed =
          metadata.target_seed ||
          metadata.target_username ||
          content?.metadata?.target_seed ||
          content?.metadata?.target_username ||
          content?.target_username;

        const schemaVersion =
          metadata.schema_version ||
          content?.metadata?.schema_version ||
          content?.schema_version;

        const seedVersion =
          metadata.seed_version ||
          metadata.execution_id ||
          metadata.trace_id ||
          content?.metadata?.seed_version ||
          content?.metadata?.execution_id ||
          content?.metadata?.trace_id;

        const sourceEntry = {
          source_account_handle: metadata.source_account_handle,
          source_profile_ref: metadata.source_profile_ref,
          target_seed: targetSeed,
          schema_version: schemaVersion,
          seed_version: seedVersion,
          artifact_id: artifact.id || artifact.artifact_id,
          captured_at: capturedAt,
          capture_method: metadata.capture_method,
        };

        const existing = byHandle.get(handle);
        if (!existing) {
          byHandle.set(handle, {
            account_id: stableId,
            handle,
            name: account.name || account.full_name || account.display_name,
            bio: account.bio || account.biography || account.profile_bio,
            profile_picture_url:
              account.profile_picture_url ||
              account.profile_pic_url ||
              account.avatar_url ||
              account.profile_image_url,
            follower_count: followerCount,
            following_count: followingCount,
            post_count: postCount,
            external_url: externalUrl,
            is_verified: account.is_verified || false,
            fetched_at: capturedAt,
            source: 'following_list',
            sources: [sourceEntry],
            category: account.category,
            tags: account.tags || [],
            public_email: account.public_email,
            public_phone_number: account.public_phone_number,
            business_address_json: account.business_address_json,
          });
        } else {
          existing.sources = mergeSourceEntry(existing.sources || [], sourceEntry);

          const overwrite = shouldOverwrite(existing.fetched_at, capturedAt);
          existing.fetched_at = overwrite ? capturedAt : existing.fetched_at;
          existing.account_id = existing.account_id || stableId;

          const nextProfilePic =
            account.profile_picture_url ||
            account.profile_pic_url ||
            account.avatar_url ||
            account.profile_image_url;
          if (overwrite && isTruthyString(nextProfilePic)) existing.profile_picture_url = nextProfilePic;
          else existing.profile_picture_url = existing.profile_picture_url || nextProfilePic;

          if (overwrite && isTruthyString(externalUrl)) existing.external_url = externalUrl;
          else existing.external_url = existing.external_url || externalUrl;

          const nextName = account.name || account.full_name || account.display_name;
          if (overwrite && isTruthyString(nextName)) existing.name = nextName;
          else existing.name = existing.name || nextName;

          const nextBio = account.bio || account.biography || account.profile_bio;
          if (overwrite && isTruthyString(nextBio)) existing.bio = nextBio;
          else existing.bio = existing.bio || nextBio;

          if (overwrite && typeof followerCount === 'number') existing.follower_count = followerCount;
          else existing.follower_count = existing.follower_count ?? followerCount;

          if (overwrite && typeof followingCount === 'number') existing.following_count = followingCount;
          else existing.following_count = existing.following_count ?? followingCount;

          if (overwrite && typeof postCount === 'number') existing.post_count = postCount;
          else existing.post_count = existing.post_count ?? postCount;

          existing.is_verified = overwrite ? !!account.is_verified : (existing.is_verified || !!account.is_verified);

          const nextEmail = account.public_email;
          if (overwrite && isTruthyString(nextEmail)) existing.public_email = nextEmail;
          else existing.public_email = existing.public_email || nextEmail;

          const nextPhone = account.public_phone_number;
          if (overwrite && isTruthyString(nextPhone)) existing.public_phone_number = nextPhone;
          else existing.public_phone_number = existing.public_phone_number || nextPhone;

          const nextAddr = account.business_address_json;
          if (overwrite && isTruthyString(nextAddr)) existing.business_address_json = nextAddr;
          else existing.business_address_json = existing.business_address_json || nextAddr;

          byHandle.set(handle, existing);
        }
      });
    }

    if (metadata.source === 'ig_account_snapshot') {
      const snapshotContent = (content?.content && typeof content.content === 'object') ? content.content : content;
      const targetHandle =
        metadata.target_account_handle ||
        snapshotContent?.target?.handle ||
        snapshotContent?.target?.username;
      if (!targetHandle) return;

      const profile = snapshotContent?.profile || {};
      const capturedAt =
        metadata.captured_at ||
        artifact.updated_at ||
        artifact.created_at ||
        new Date().toISOString();

      const followerCount =
        profile.follower_count ?? parseCountTextToNumber(profile.follower_count_text);
      const followingCount =
        profile.following_count ?? parseCountTextToNumber(profile.following_count_text);
      const postCount =
        profile.post_count ?? parseCountTextToNumber(profile.post_count_text);

      const externalUrl =
        profile.external_url ||
        snapshotContent?.target?.external_url ||
        undefined;

      const schemaVersion =
        metadata.schema_version ||
        snapshotContent?.metadata?.schema_version ||
        'ig.account_snapshot.v1';

      const seedVersion =
        metadata.seed_version ||
        metadata.execution_id ||
        metadata.trace_id ||
        snapshotContent?.metadata?.seed_version ||
        snapshotContent?.metadata?.execution_id ||
        snapshotContent?.metadata?.trace_id;

      const sourceEntry = {
        source_account_handle: metadata.source_account_handle,
        source_profile_ref: metadata.source_profile_ref,
        target_seed: metadata.target_seed,
        schema_version: schemaVersion,
        seed_version: seedVersion,
        artifact_id: artifact.id || artifact.artifact_id,
        captured_at: capturedAt,
        capture_method: 'snapshot',
      };

      const stableId = `${artifact.id || artifact.artifact_id}_${targetHandle}`;
      const existing = byHandle.get(targetHandle);

      if (!existing) {
        byHandle.set(targetHandle, {
          account_id: stableId,
          handle: targetHandle,
          name: undefined,
          bio: profile.bio || undefined,
          profile_picture_url: profile.avatar_url || undefined,
          follower_count: typeof followerCount === 'number' ? followerCount : undefined,
          following_count: typeof followingCount === 'number' ? followingCount : undefined,
          post_count: typeof postCount === 'number' ? postCount : undefined,
          external_url: externalUrl,
          is_verified: !!profile.is_verified,
          fetched_at: capturedAt,
          source: 'browser_session',
          sources: [sourceEntry],
          tags: [],
        });
      } else {
        existing.sources = mergeSourceEntry(existing.sources || [], sourceEntry);
        const overwrite = shouldOverwrite(existing.fetched_at, capturedAt);
        existing.fetched_at = overwrite ? capturedAt : existing.fetched_at;
        existing.account_id = existing.account_id || stableId;

        const nextBio = profile.bio;
        if (overwrite && isTruthyString(nextBio)) existing.bio = nextBio;
        else existing.bio = existing.bio || nextBio;

        const nextAvatar = profile.avatar_url;
        if (overwrite && isTruthyString(nextAvatar)) existing.profile_picture_url = nextAvatar;
        else existing.profile_picture_url = existing.profile_picture_url || nextAvatar;

        if (overwrite && typeof followerCount === 'number') existing.follower_count = followerCount;
        else existing.follower_count = existing.follower_count ?? (typeof followerCount === 'number' ? followerCount : undefined);

        if (overwrite && typeof followingCount === 'number') existing.following_count = followingCount;
        else existing.following_count = existing.following_count ?? (typeof followingCount === 'number' ? followingCount : undefined);

        if (overwrite && typeof postCount === 'number') existing.post_count = postCount;
        else existing.post_count = existing.post_count ?? (typeof postCount === 'number' ? postCount : undefined);

        if (overwrite && isTruthyString(externalUrl)) existing.external_url = externalUrl;
        else existing.external_url = existing.external_url || externalUrl;

        existing.is_verified = overwrite ? !!profile.is_verified : (existing.is_verified || !!profile.is_verified);
        byHandle.set(targetHandle, existing);
      }
    }
  });

  return Array.from(byHandle.values());
}
