"""fold findings duplicated before fingerprints into one report each

Scans that ran before 0003 wrote the same finding up once per scan. Each group
of reports with the same fingerprint keeps one report (the first one a
reviewer decided on, else the first written), which takes the group's seen
count and latest sighting; the others point at it through
duplicate_of and drop out of the feed and the review queue. Runs that were only
waiting on such copies are marked superseded, since the first report's run
carries the review. Nothing is deleted, and every fold is written to the ledger.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FOLD = """
with ranked as (
    select id, fingerprint,
           first_value(id) over w as keeper,
           row_number() over w as n,
           sum(seen_count) over (partition by fingerprint) as seen,
           max(last_seen_at) over (partition by fingerprint) as last_seen
      from incident_reports
     where duplicate_of is null
    window w as (partition by fingerprint order by review_decision is null, created_at, id)
),
kept as (
    update incident_reports r
       set seen_count = k.seen, last_seen_at = k.last_seen
      from ranked k
     where r.id = k.id and k.n = 1 and k.seen > r.seen_count
    returning r.id
),
folded as (
    update incident_reports r
       set duplicate_of = k.keeper
      from ranked k
     where r.id = k.id and k.n > 1
    returning r.id, r.duplicate_of, r.run_id
)
insert into audit_ledger (actor, action, subject, payload)
select 'migration:0004', 'finding.merged', f.id::text,
       jsonb_build_object('into', f.duplicate_of::text, 'run_id', f.run_id::text)
  from folded f
"""

SUPERSEDE = """
update agent_runs a
   set status = 'superseded'
 where a.status = 'paused_review'
   and exists (
       select 1 from incident_reports r where r.run_id = a.id and r.duplicate_of is not null
   )
   and not exists (
       select 1 from incident_reports r
        where r.run_id = a.id and r.status = 'pending_review' and r.duplicate_of is null
   )
"""


def upgrade() -> None:
    op.add_column(
        "incident_reports",
        sa.Column(
            "duplicate_of",
            UUID(as_uuid=True),
            sa.ForeignKey("incident_reports.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_incident_reports_duplicate_of", "incident_reports", ["duplicate_of"])
    op.execute(FOLD)
    op.execute(SUPERSEDE)


def downgrade() -> None:
    op.drop_index("ix_incident_reports_duplicate_of", table_name="incident_reports")
    op.drop_column("incident_reports", "duplicate_of")
