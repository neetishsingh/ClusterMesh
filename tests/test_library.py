"""Tests for agent library manager."""

from mesh.agent.library import LibraryManager, InstalledLibrary


class TestLibraryManager:
    def test_installed_library(self):
        lib = InstalledLibrary(name="numpy", version="2.0")
        assert lib.name == "numpy"

    def test_has_after_manual_add(self):
        mgr = LibraryManager()
        mgr._installed["pandas"] = InstalledLibrary(name="pandas", version="2.3")
        assert mgr.has("pandas")
        assert not mgr.has("torch")

    def test_list_names(self):
        mgr = LibraryManager()
        mgr._installed["numpy"] = InstalledLibrary(name="numpy", version="2.0")
        mgr._installed["pandas"] = InstalledLibrary(name="pandas", version="2.3")
        assert mgr.list_names() == ["numpy", "pandas"]
