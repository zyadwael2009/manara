"""Authorization for `/media/<path>` reads.

Uploaded files are not free-standing: every one of them is *referenced* by
exactly one of a small set of columns, and the permission question "may this
caller read this file?" reduces to the permission question already answered
for whatever references it.

Only four columns in the whole schema hold a URL:

  * `courses.thumbnail_url`             -> catalog art, published courses are
                                          a public read already
  * `lessons.content_url`               -> `can_view_lesson_content`
  * `assignment_submissions.file_url`   -> `can_view_student_records`
                                          (plus the submitter and their group)
  * `timetable_periods.meeting_url`     -> an external Meet/Zoom link, never
                                          a `/media/` path, so it is not
                                          consulted here

So the resolver checks those three, falling back to owner-or-admin for a file
that nothing references yet (freshly uploaded, or attached to a draft the
uploader has not saved).
"""
from __future__ import annotations

from models import (
    AssignmentSubmission,
    Course,
    Lesson,
    UploadedFile,
    User,
    db,
)
from utils.permissions import (
    can_view_lesson_content,
    can_view_student_records,
    is_admin,
)


def _referencing_submission(url: str) -> AssignmentSubmission | None:
    return AssignmentSubmission.query.filter_by(file_url=url).first()


def _referencing_lesson(url: str) -> Lesson | None:
    return Lesson.query.filter_by(content_url=url).first()


def _course_thumbnail_is(url: str) -> Course | None:
    return Course.query.filter_by(thumbnail_url=url).first()


def _can_read_submission(user: User, sub: AssignmentSubmission) -> bool:
    """The submitter, their group peers, and anyone who may see the
    submitter's records (admin, homeroom, course teacher, linked parent)."""
    if sub.student_id == user.id:
        return True
    if can_view_student_records(user, sub.student):
        return True
    # Group assignments: every member shares one artefact, so a peer in the
    # same group is as entitled to read it as the member who uploaded it.
    if sub.group_id:
        peer = AssignmentSubmission.query.filter_by(
            group_id=sub.group_id, student_id=user.id,
        ).first()
        if peer is not None:
            return True
    return False


def can_read_upload(user: User | None, stored_path: str) -> bool:
    """Return True if `user` may read `instance/uploads/<stored_path>`.

    `user` is never None in practice — `routes/media.py` gates on
    `@login_required` first — but the None case is handled so this stays
    usable as a plain predicate.
    """
    if user is None:
        return False
    if is_admin(user):
        return True

    url = f"/media/{stored_path}"
    record = UploadedFile.query.filter_by(stored_path=stored_path).first()

    # The uploader can always read their own file back — this is what lets a
    # student re-open the essay they just attached but have not yet submitted.
    if record is not None and record.owner_id == user.id:
        return True

    sub = _referencing_submission(url)
    if sub is not None:
        return _can_read_submission(user, sub)

    lesson = _referencing_lesson(url)
    if lesson is not None:
        return can_view_lesson_content(user, lesson)

    course = _course_thumbnail_is(url)
    if course is not None:
        # Catalog thumbnails ride along with the catalog read, which is
        # public for published courses; drafts stay staff-only.
        if course.status == "published":
            return True
        from utils.permissions import can_edit_course_content

        return can_edit_course_content(user, course)

    # Nothing references it. Only the uploader (handled above) and admins get
    # in — a file in limbo is not a shared resource.
    return False


def register_upload(
    *,
    stored_path: str,
    kind: str,
    owner_id: str | None,
    size_bytes: int,
    content_type: str | None,
) -> UploadedFile:
    """Record an accepted upload. Called from `routes/uploads.py`."""
    row = UploadedFile(
        stored_path=stored_path,
        kind=kind,
        owner_id=owner_id,
        size_bytes=size_bytes,
        content_type=content_type or None,
    )
    db.session.add(row)
    db.session.commit()
    return row
