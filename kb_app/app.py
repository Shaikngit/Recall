from __future__ import annotations

from flask import Flask, jsonify, render_template, request

from kb_app.ai import AIHelper, AISettings, AISettingsStore
from kb_app.core import (
    app_status,
    append_to_daily_inbox,
    build_capture_clarification,
    build_fallback_answer,
    dump_results_for_prompt,
    get_content_library_status,
    get_note_document,
    get_recent_notes,
    import_content_library,
    initialize_content_root,
    organize_inbox,
    relative_note_path,
    resolve_search_scope,
    resolve_capture_clarification,
    save_detailed_capture,
    save_quick_tip,
    search_notes,
    select_display_results,
    suggest_destinations,
)


def create_app() -> Flask:
    app = Flask(__name__)
    initialize_content_root()
    settings_store = AISettingsStore()

    def current_ai_helper() -> AIHelper:
        return AIHelper.from_settings(settings_store.load())

    @app.get("/")
    def index() -> str:
        ai_helper = current_ai_helper()
        return render_template(
            "index.html",
            recent_notes=get_recent_notes(),
            status=app_status(ai_helper),
            model_settings=settings_store.load().to_public_dict(),
        )

    @app.get("/healthz")
    def healthz() -> object:
        return jsonify({"status": "ok"})

    @app.get("/api/recent")
    def recent() -> object:
        return jsonify(get_recent_notes())

    @app.get("/api/note")
    def note() -> object:
        relative_path_value = str(request.args.get("path", "")).strip()
        if not relative_path_value:
            return jsonify({"error": "Note path is required."}), 400

        note_document = get_note_document(relative_path_value)
        if note_document is None:
            return jsonify({"error": "Note not found."}), 404

        return jsonify(
            {
                "path": relative_note_path(note_document.path),
                "title": note_document.title,
                "content": note_document.content,
            }
        )

    @app.get("/api/status")
    def status() -> object:
        ai_helper = current_ai_helper()
        return jsonify(app_status(ai_helper))

    @app.get("/api/content/status")
    def content_status() -> object:
        return jsonify(get_content_library_status())

    @app.post("/api/content/import")
    def import_content() -> object:
        payload = request.get_json(silent=True) or {}
        raw_paths = payload.get("paths") or []
        relative_paths = [str(path).strip() for path in raw_paths if str(path).strip()]
        return jsonify(import_content_library(relative_paths or None))

    @app.get("/api/model-settings")
    def get_model_settings() -> object:
        return jsonify(settings_store.load().to_public_dict())

    @app.post("/api/model-settings")
    def save_model_settings() -> object:
        payload = request.get_json(silent=True) or {}
        existing = settings_store.load()
        settings = AISettings.from_payload(
            {
                "provider": payload.get("provider", existing.provider),
                "model": payload.get("model", existing.model),
                "baseUrl": payload.get("baseUrl", existing.base_url),
                "apiKey": payload.get("apiKey") if payload.get("apiKey") else existing.api_key,
            }
        )
        settings_store.save(settings)
        return jsonify({"message": "Model settings saved.", "settings": settings.to_public_dict()})

    @app.post("/api/model-settings/test")
    def test_model_settings() -> object:
        payload = request.get_json(silent=True) or {}
        existing = settings_store.load()
        settings = AISettings.from_payload(
            {
                "provider": payload.get("provider", existing.provider),
                "model": payload.get("model", existing.model),
                "baseUrl": payload.get("baseUrl", existing.base_url),
                "apiKey": payload.get("apiKey") if payload.get("apiKey") else existing.api_key,
            }
        )
        helper = AIHelper.from_settings(settings)
        ok, message = helper.test_connection()
        if not ok:
            return jsonify({"ok": False, "message": message}), 400
        return jsonify({"ok": True, "message": message, "settings": settings.to_public_dict()})

    @app.post("/api/capture")
    def capture() -> object:
        image_file = None
        if request.content_type and request.content_type.startswith("multipart/form-data"):
            raw_note = str(request.form.get("note", "")).strip()
            capture_mode = str(request.form.get("mode", "detailed")).strip().lower()
            image_file = request.files.get("image")
        else:
            payload = request.get_json(silent=True) or {}
            raw_note = str(payload.get("note", "")).strip()
            capture_mode = str(payload.get("mode", "detailed")).strip().lower()
        if not raw_note:
            return jsonify({"error": "Note text is required."}), 400

        if capture_mode == "quick":
            saved_path = save_quick_tip(raw_note)
            return jsonify(
                {
                    "message": "Quick tip saved.",
                    "savedTo": relative_note_path(saved_path),
                    "suggestedDestinations": [],
                    "autoOrganized": {"organized": [], "keptFiles": [], "deletedFiles": []},
                    "needsClarification": None,
                }
            )

        ai_helper = current_ai_helper()
        screenshot_bytes = image_file.read() if image_file and image_file.filename else None
        if screenshot_bytes is not None and not screenshot_bytes:
            screenshot_bytes = None
        try:
            direct_saved = save_detailed_capture(
                raw_note,
                ai_helper if ai_helper.is_configured else None,
                screenshot_bytes=screenshot_bytes,
                screenshot_filename=image_file.filename if image_file and image_file.filename else None,
                screenshot_mime_type=image_file.mimetype if image_file and image_file.mimetype else None,
            )
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        if direct_saved is not None:
            return jsonify(
                {
                    "message": "Note saved.",
                    "savedTo": direct_saved["destination"],
                    "suggestedDestinations": [],
                    "autoOrganized": {
                        "organized": [
                            {
                                "source": "",
                                "destination": direct_saved["destination"],
                                "title": direct_saved["title"],
                                "summary": direct_saved["summary"],
                                "captureId": "",
                            }
                        ],
                        "keptFiles": [],
                        "deletedFiles": [],
                    },
                    "needsClarification": None,
                }
            )

        saved_path, capture_id = append_to_daily_inbox(raw_note)
        suggestions = suggest_destinations(raw_note)
        auto_organize_result = organize_inbox(
            ai_helper if ai_helper.is_configured else None,
            inbox_paths=[saved_path],
        )
        current_capture_organized = any(
            item.get("captureId") == capture_id for item in auto_organize_result.get("organized", [])
        )
        clarification = None
        if not current_capture_organized:
            clarification = build_capture_clarification(raw_note, capture_id, saved_path)

        return jsonify(
            {
                "message": "Note saved.",
                "savedTo": saved_path.name if saved_path.parent.name == "Inbox" else relative_note_path(saved_path),
                "suggestedDestinations": suggestions,
                "autoOrganized": auto_organize_result,
                "needsClarification": clarification,
            }
        )

    @app.post("/api/capture/resolve")
    def resolve_capture() -> object:
        payload = request.get_json(silent=True) or {}
        capture_id = str(payload.get("captureId", "")).strip()
        destination_key = str(payload.get("destinationKey", "")).strip()
        custom_title = str(payload.get("title", "")).strip()
        saved_to = str(payload.get("savedTo", "")).strip()

        if not capture_id:
            return jsonify({"error": "Capture ID is required."}), 400
        if not destination_key:
            return jsonify({"error": "Choose a KB destination to continue."}), 400

        inbox_path = None
        if saved_to:
            normalized_path = saved_to.replace("\\", "/").lstrip("/")
            inbox_path = initialize_content_root() / normalized_path

        ai_helper = current_ai_helper()
        try:
            resolved = resolve_capture_clarification(
                capture_id,
                destination_key,
                custom_title=custom_title,
                inbox_path=inbox_path,
                ai_helper=ai_helper if ai_helper.is_configured else None,
            )
        except ValueError as error:
            return jsonify({"error": str(error)}), 400

        return jsonify(
            {
                "message": "Capture organized.",
                "resolved": resolved,
            }
        )

    @app.post("/api/ask")
    def ask() -> object:
        payload = request.get_json(silent=True) or {}
        query = str(payload.get("query", "")).strip()
        history = payload.get("history") or []
        ai_helper = current_ai_helper()
        if not query:
            return jsonify({"error": "Question text is required."}), 400
        if not ai_helper.is_configured:
            return jsonify({"error": "AI is required for recall. Open Settings and configure a model before asking questions."}), 503

        search_scope = resolve_search_scope(query)
        effective_query = search_scope.query or (f"summarize notes in {search_scope.label}" if search_scope.is_scoped else query)
        results = search_notes(search_scope.query, search_root=search_scope.root)
        fallback_answer = build_fallback_answer(effective_query, results)
        answer = ai_helper.answer_question(effective_query, dump_results_for_prompt(results), history=history) or fallback_answer
        display_results = select_display_results(results, effective_query)
        result_payload = [
            {
                "path": relative_note_path(result.path),
                "title": result.title,
                "snippet": result.snippet,
                "score": result.score,
            }
            for result in display_results
        ]

        return jsonify(
            {
                "answer": answer,
                "aiUsed": answer != fallback_answer,
                "results": result_payload,
            }
        )

    @app.post("/api/organize")
    def organize() -> object:
        ai_helper = current_ai_helper()
        result = organize_inbox(ai_helper if ai_helper.is_configured else None)
        return jsonify(result)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8765, debug=True, use_reloader=False)
