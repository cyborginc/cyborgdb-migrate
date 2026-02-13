import pytest

from cyborgdb_migrate.app import MigrateApp
from cyborgdb_migrate.models import MigrationState
from cyborgdb_migrate.screens.source_select import SourceSelectScreen
from cyborgdb_migrate.screens.welcome import WelcomeScreen
from cyborgdb_migrate.widgets.key_warning import KeyWarningModal


class TestAppStartup:
    @pytest.mark.asyncio
    async def test_app_starts_on_welcome(self):
        app = MigrateApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            assert isinstance(app.screen, WelcomeScreen)

    @pytest.mark.asyncio
    async def test_get_started_navigates_to_source_select(self):
        app = MigrateApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.screen.query_one("#get-started-btn").press()
            await pilot.pause()
            assert isinstance(app.screen, SourceSelectScreen)

    @pytest.mark.asyncio
    async def test_source_list_shows_6_sources(self):
        app = MigrateApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.screen.query_one("#get-started-btn").press()
            await pilot.pause()
            from textual.widgets import OptionList

            option_list = app.screen.query_one("#source-list", OptionList)
            assert option_list.option_count == 6

    @pytest.mark.asyncio
    async def test_app_has_title(self):
        app = MigrateApp()
        async with app.run_test() as pilot:
            assert app.title == "CyborgDB Migration Wizard"


class TestKeyWarningModal:
    @pytest.mark.asyncio
    async def test_continue_disabled_by_default(self):
        app = MigrateApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.push_screen(KeyWarningModal("/tmp/test.key"))
            await pilot.pause()

            from textual.widgets import Button

            btn = app.screen.query_one("#continue-btn", Button)
            assert btn.disabled is True

    @pytest.mark.asyncio
    async def test_continue_enabled_on_i_understand(self):
        app = MigrateApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.push_screen(KeyWarningModal("/tmp/test.key"))
            await pilot.pause()

            from textual.widgets import Button, Input

            inp = app.screen.query_one("#confirm-input", Input)
            inp.value = "I understand"
            await pilot.pause()

            btn = app.screen.query_one("#continue-btn", Button)
            assert btn.disabled is False

    @pytest.mark.asyncio
    async def test_continue_blocked_on_wrong_text(self):
        app = MigrateApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.push_screen(KeyWarningModal("/tmp/test.key"))
            await pilot.pause()

            from textual.widgets import Button, Input

            inp = app.screen.query_one("#confirm-input", Input)
            inp.value = "sure"
            await pilot.pause()

            btn = app.screen.query_one("#continue-btn", Button)
            assert btn.disabled is True
