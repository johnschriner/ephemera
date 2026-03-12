import os
from datetime import datetime, timezone

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash
)
from dotenv import load_dotenv

load_dotenv()

from config import Config
from models import init_db, get_db
from storage import allowed_file, prepare_upload
from r2_storage import (
    upload_fileobj_to_r2,
    delete_from_r2,
    list_r2_objects,
    get_object_metadata,
    infer_media_type_from_key,
    update_object_metadata,
    get_public_url,
)

app = Flask(__name__)
app.config.from_object(Config)

with app.app_context():
    init_db()

_bucket_restore_checked = False


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_db_restored_from_r2():
    global _bucket_restore_checked

    if _bucket_restore_checked:
        return

    db = get_db()
    row = db.execute("SELECT COUNT(*) AS count FROM images").fetchone()
    count = row["count"] if row else 0

    if count > 0:
        _bucket_restore_checked = True
        return

    objects = list_r2_objects()

    for obj in objects:
        key = obj["key"]
        metadata = get_object_metadata(key)

        caption = metadata.get("caption", "").strip()
        status = metadata.get("status", "").strip().lower() or "approved"
        if status not in {"pending", "approved"}:
            status = "approved"

        media_type = metadata.get("media_type", "").strip().lower()
        if media_type not in {"image", "video"}:
            media_type = infer_media_type_from_key(key) or "image"

        uploaded_at = metadata.get("uploaded_at", "").strip()
        if not uploaded_at:
            last_modified = obj.get("last_modified")
            if last_modified:
                uploaded_at = last_modified.astimezone(timezone.utc).isoformat()
            else:
                uploaded_at = now_iso()

        db.execute(
            """
            INSERT INTO images
            (filename, file_url, storage_key, caption, status, media_type, uploaded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (key, get_public_url(key), key, caption, status, media_type, uploaded_at),
        )

    db.commit()
    _bucket_restore_checked = True


def enforce_approved_limit():
    db = get_db()

    approved = db.execute(
        """
        SELECT id, filename, storage_key
        FROM images
        WHERE status = 'approved'
        ORDER BY uploaded_at DESC, id DESC
        """
    ).fetchall()

    max_items = app.config["MAX_APPROVED_IMAGES"]

    if len(approved) <= max_items:
        return

    to_delete = approved[max_items:]

    for row in to_delete:
        if row["storage_key"]:
            delete_from_r2(row["storage_key"])
        else:
            path = os.path.join(app.config["UPLOAD_FOLDER"], row["filename"])
            if os.path.exists(path):
                os.remove(path)

        db.execute("DELETE FROM images WHERE id = ?", (row["id"],))

    db.commit()


def cleanup_old_pending():
    db = get_db()

    old = db.execute(
        """
        SELECT id, filename, storage_key
        FROM images
        WHERE status = 'pending'
        AND uploaded_at < datetime('now', '-7 days')
        """
    ).fetchall()

    for row in old:
        if row["storage_key"]:
            delete_from_r2(row["storage_key"])
        else:
            path = os.path.join(app.config["UPLOAD_FOLDER"], row["filename"])
            if os.path.exists(path):
                os.remove(path)

        db.execute("DELETE FROM images WHERE id = ?", (row["id"],))

    db.commit()


@app.route("/")
def gallery():
    ensure_db_restored_from_r2()
    cleanup_old_pending()

    db = get_db()
    rows = db.execute(
        """
        SELECT *
        FROM images
        WHERE status IN ('pending', 'approved')
        ORDER BY uploaded_at DESC, id DESC
        """
    ).fetchall()

    images = [dict(row) for row in rows]

    approved_positions = [i for i, img in enumerate(images) if img["status"] == "approved"]
    fading_positions = set(approved_positions[-5:]) if approved_positions else set()

    for i, img in enumerate(images):
        img["fading"] = i in fading_positions

    return render_template("gallery.html", images=images)


@app.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        file = request.files.get("image")
        caption = request.form.get("caption", "").strip()

        if not file or not file.filename:
            flash("Please choose a file.", "error")
            return redirect(url_for("upload"))

        if not allowed_file(file.filename):
            flash("Unsupported file type.", "error")
            return redirect(url_for("upload"))

        try:
            prepared_file, media_type = prepare_upload(file)
            uploaded_at = now_iso()

            storage_key, file_url = upload_fileobj_to_r2(
                prepared_file,
                file.filename,
                file.content_type,
                caption=caption,
                status="pending",
                media_type=media_type,
                uploaded_at=uploaded_at,
            )

            db = get_db()
            db.execute(
                """
                INSERT INTO images
                (filename, file_url, storage_key, caption, status, media_type, uploaded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (file.filename, file_url, storage_key, caption, "pending", media_type, uploaded_at),
            )
            db.commit()

            flash("Uploaded. Marked for approval.", "success")
            return redirect(url_for("gallery"))

        except Exception as e:
            app.logger.exception("Upload failed")
            flash(f"Upload failed: {e}", "error")
            return redirect(url_for("upload"))

    return render_template("upload.html")


@app.route("/image/<int:image_id>")
def image(image_id):
    ensure_db_restored_from_r2()

    db = get_db()
    image = db.execute(
        """
        SELECT *
        FROM images
        WHERE id = ?
        AND status IN ('pending', 'approved')
        """,
        (image_id,)
    ).fetchone()

    if not image:
        flash("That item does not exist.", "error")
        return redirect(url_for("gallery"))

    return render_template("image.html", image=image)


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        password = request.form.get("password")

        if password == app.config["ADMIN_PASSWORD"]:
            session["admin"] = True
            return redirect(url_for("admin_dashboard"))

        flash("Incorrect password.", "error")

    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("gallery"))


@app.route("/admin")
def admin_dashboard():
    ensure_db_restored_from_r2()

    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    db = get_db()

    pending = db.execute(
        "SELECT * FROM images WHERE status = 'pending' ORDER BY uploaded_at DESC, id DESC"
    ).fetchall()

    approved = db.execute(
        "SELECT * FROM images WHERE status = 'approved' ORDER BY uploaded_at DESC, id DESC LIMIT 50"
    ).fetchall()

    return render_template("admin.html", pending=pending, approved=approved)


@app.route("/admin/approve/<int:image_id>", methods=["POST"])
def approve(image_id):
    ensure_db_restored_from_r2()

    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    db = get_db()
    row = db.execute(
        """
        SELECT id, storage_key, caption, media_type, uploaded_at
        FROM images
        WHERE id = ?
        """,
        (image_id,)
    ).fetchone()

    if not row:
        flash("That item does not exist.", "error")
        return redirect(url_for("admin_dashboard"))

    db.execute(
        "UPDATE images SET status = 'approved' WHERE id = ?",
        (image_id,)
    )
    db.commit()

    if row["storage_key"]:
        update_object_metadata(
            key=row["storage_key"],
            caption=row["caption"] or "",
            status="approved",
            media_type=row["media_type"] or infer_media_type_from_key(row["storage_key"]) or "image",
            uploaded_at=row["uploaded_at"] or now_iso(),
        )

    enforce_approved_limit()
    flash("Approved.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/reject/<int:image_id>", methods=["POST"])
def reject(image_id):
    ensure_db_restored_from_r2()

    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    db = get_db()

    row = db.execute(
        "SELECT filename, storage_key FROM images WHERE id = ?",
        (image_id,)
    ).fetchone()

    if row:
        if row["storage_key"]:
            delete_from_r2(row["storage_key"])
        else:
            path = os.path.join(app.config["UPLOAD_FOLDER"], row["filename"])
            if os.path.exists(path):
                os.remove(path)

    db.execute("DELETE FROM images WHERE id = ?", (image_id,))
    db.commit()

    flash("Removed.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/terms")
def terms():
    return render_template("terms.html")


if __name__ == "__main__":
    app.run(debug=True)