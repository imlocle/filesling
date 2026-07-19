"""
Tests for the credential storage service.
"""

from unittest.mock import patch

from src.services.keychain_service import (
    delete_password,
    has_stored_password,
    retrieve_password,
    store_password,
)


class TestStorePassword:
    @patch("src.services.keychain_service.store_credential")
    def test_store_success(self, mock_store):
        mock_store.return_value = True
        result = store_password("user@host", "secret123")
        assert result is True
        mock_store.assert_called_once_with("user@host", "secret123")

    @patch("src.services.keychain_service.store_credential")
    def test_store_failure(self, mock_store):
        mock_store.return_value = False
        result = store_password("user@host", "secret123")
        assert result is False


class TestRetrievePassword:
    @patch("src.services.keychain_service.get_credential")
    def test_retrieve_success(self, mock_get):
        mock_get.return_value = "secret123"
        result = retrieve_password("user@host")
        assert result == "secret123"

    @patch("src.services.keychain_service.get_credential")
    def test_retrieve_not_found(self, mock_get):
        mock_get.return_value = None
        result = retrieve_password("user@host")
        assert result is None


class TestDeletePassword:
    @patch("src.services.keychain_service.delete_credential")
    def test_delete_success(self, mock_delete):
        mock_delete.return_value = True
        result = delete_password("user@host")
        assert result is True

    @patch("src.services.keychain_service.delete_credential")
    def test_delete_not_found(self, mock_delete):
        mock_delete.return_value = False
        result = delete_password("user@host")
        assert result is False


class TestHasStoredPassword:
    @patch("src.services.keychain_service.has_credential")
    def test_has_password(self, mock_has):
        mock_has.return_value = True
        assert has_stored_password("user@host") is True

    @patch("src.services.keychain_service.has_credential")
    def test_no_password(self, mock_has):
        mock_has.return_value = False
        assert has_stored_password("user@host") is False
