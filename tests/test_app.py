import io
import json
import unittest
import os
import logging
from unittest.mock import MagicMock, mock_open, patch
logging.disable(logging.CRITICAL)

from app.utils import safe_relative_path, safe_path, SERVE_DIRECTORY
from app.translations import TRANSLATIONS
from app import app

class TestMSXServer(unittest.TestCase):
    def test_safe_relative_path(self):
        # Good paths
        self.assertEqual(safe_relative_path("test/file.txt"), "test/file.txt")
        self.assertEqual(safe_relative_path(""), "")
        
        # Dangerous paths should raise ValueError
        with self.assertRaises(ValueError):
            safe_relative_path("../outside.txt")
        with self.assertRaises(ValueError):
            safe_relative_path("/absolute/path")

    def test_safe_path(self):
        # Should stay within SERVE_DIRECTORY
        path = safe_path("subdir/game.rom")
        self.assertTrue(path.startswith(os.path.abspath(SERVE_DIRECTORY)))

    def test_translations(self):
        # Verify both languages exist and have same keys
        self.assertIn("nl", TRANSLATIONS)
        self.assertIn("en", TRANSLATIONS)
        nl_keys = set(TRANSLATIONS["nl"].keys())
        en_keys = set(TRANSLATIONS["en"].keys())
        self.assertEqual(nl_keys, en_keys, "NL and EN translation keys must match!")

    def test_timestamp_filename(self):
        from app.utils import timestamp_filename
        from datetime import datetime
        fixed_dt = datetime(2026, 10, 6, 18, 30, 45)
        stamped = timestamp_filename("game.rom", dt=fixed_dt)
        self.assertEqual(stamped, "20261006_183045_game.rom")

class TestAPIEndpoints(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()
        os.makedirs(SERVE_DIRECTORY, exist_ok=True)

    def test_api_upload_download_delete_flow(self):
        # 1. Test File Upload via API
        test_filename = "test_api_file.rom"
        test_content = b"MSX_TEST_DATA_12345"
        
        data = {
            'file': (io.BytesIO(test_content), test_filename),
            'target_dir': ''
        }
        res = self.client.post('/api/upload', data=data, content_type='multipart/form-data')
        self.assertEqual(res.status_code, 201)
        res_json = res.get_json()
        self.assertTrue(res_json['success'])
        uploaded_filename = res_json['filename']
        self.assertTrue(uploaded_filename.endswith(f"_{test_filename}"))
        
        uploaded_path = os.path.join(SERVE_DIRECTORY, uploaded_filename)
        self.assertTrue(os.path.exists(uploaded_path))

        # 2. Test File List API
        res = self.client.get('/api/files')
        self.assertEqual(res.status_code, 200)
        res_json = res.get_json()
        self.assertTrue(res_json['success'])
        file_names = [f['name'] for f in res_json['files']]
        self.assertIn(uploaded_filename, file_names)

        # 3. Test File Download via Path
        res = self.client.get(f'/api/download/{uploaded_filename}')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data, test_content)
        res.close()

        # Test File Download via Query Param
        res = self.client.get(f'/api/download?path={uploaded_filename}')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data, test_content)
        res.close()

        # 4. Test File Delete via API (POST JSON)
        res = self.client.post('/api/delete', json={'path': uploaded_filename})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()['success'])
        self.assertFalse(os.path.exists(uploaded_path))

    def test_api_upload_adds_timestamp(self):
        test_filename = "unique_stamp_test.rom"
        test_content = b"TIMESTAMP_TEST"

        data = {
            'file': (io.BytesIO(test_content), test_filename),
            'target_dir': ''
        }
        res = self.client.post('/api/upload', data=data, content_type='multipart/form-data')
        self.assertEqual(res.status_code, 201)
        res_json = res.get_json()
        saved_name = res_json['filename']
        
        import re
        self.assertTrue(re.match(r"^\d{8}_\d{6}_unique_stamp_test\.rom$", saved_name))
        
        uploaded_path = os.path.join(SERVE_DIRECTORY, saved_name)
        self.assertTrue(os.path.exists(uploaded_path))
        if os.path.exists(uploaded_path):
            os.remove(uploaded_path)

    def test_api_delete_via_http_delete_method(self):
        # Create dummy file to delete
        dummy_file = os.path.join(SERVE_DIRECTORY, "to_delete.txt")
        with open(dummy_file, "w") as f:
            f.write("delete me")
        
        res = self.client.delete('/api/delete?path=to_delete.txt')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()['success'])
        self.assertFalse(os.path.exists(dummy_file))

    def test_api_error_handling(self):
        # Download non-existent file
        res = self.client.get('/api/download/non_existent_file.rom')
        self.assertEqual(res.status_code, 404)
        self.assertFalse(res.get_json()['success'])

        # Delete non-existent file
        res = self.client.post('/api/delete', json={'path': 'non_existent.rom'})
        self.assertEqual(res.status_code, 404)

        # Invalid path traversal attempt
        res = self.client.post('/api/delete', json={'path': '../outside.txt'})
        self.assertEqual(res.status_code, 400)

    def test_index2_all_types_and_uploaded_at(self):
        # Create a test ROM file
        test_file = os.path.join(SERVE_DIRECTORY, "recent_test.rom")
        with open(test_file, "wb") as f:
            f.write(b"RECENT_TEST")

        res = self.client.get('/index2.php/?type=ALL&char=a&web=1')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIsInstance(data, list)
        found = [item for item in data if item['path'] == 'recent_test.rom']
        self.assertEqual(len(found), 1)
        self.assertIn('uploaded_at', found[0])
        self.assertIsNotNone(found[0]['uploaded_at'])

        # Clean up
        if os.path.exists(test_file):
            os.remove(test_file)

    def test_index2_sorting_newest_first(self):
        # Create two files with different mtimes
        import time
        file_old = os.path.join(SERVE_DIRECTORY, "old_test.rom")
        file_new = os.path.join(SERVE_DIRECTORY, "new_test.rom")

        with open(file_old, "wb") as f:
            f.write(b"OLD")
        # set mtime in past
        os.utime(file_old, (time.time() - 100, time.time() - 100))

        with open(file_new, "wb") as f:
            f.write(b"NEW")
        # set mtime to now
        os.utime(file_new, (time.time(), time.time()))

        res = self.client.get('/index2.php/?type=ALL&char=a&web=1')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        # Find the indexes of both files in the list
        idx_old = next((i for i, item in enumerate(data) if item['path'] == 'old_test.rom'), None)
        idx_new = next((i for i, item in enumerate(data) if item['path'] == 'new_test.rom'), None)

        self.assertIsNotNone(idx_old)
        self.assertIsNotNone(idx_new)
        # New file should be before old file
        self.assertTrue(idx_new < idx_old, "Newest file should appear first")

        # Clean up
        for path in (file_old, file_new):
            if os.path.exists(path):
                os.remove(path)

    def test_swagger_and_openapi(self):
        # 1. Test openapi.yaml route
        res = self.client.get('/docs/openapi.yaml')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'openapi: 3.0.3', res.data)
        res.close()

        # 2. Test swagger UI routes
        for url in ('/docs', '/docs/', '/swagger', '/swagger/'):
            res = self.client.get(url)
            self.assertEqual(res.status_code, 200)
            self.assertIn(b'SwaggerUIBundle', res.data)
            res.close()

    def test_api_network_info(self):
        res = self.client.get('/api/network-info', headers={'Host': '192.168.1.100'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertIn('docker_ip', data)
        self.assertIn('machine_ip', data)
        self.assertEqual(data['machine_ip'], '192.168.1.100')
        self.assertEqual(data['url_txt_machine'], 'http://192.168.1.100/')
        res.close()

    def test_api_network_info_falls_back_to_host_ipv4(self):
        addresses = [
            (0, 0, 0, '', ('127.0.0.1', 0)),
            (0, 0, 0, '', ('192.168.1.42', 0)),
        ]
        with patch('app.server.socket.socket', side_effect=OSError), \
                patch('app.server.socket.getaddrinfo', return_value=addresses), \
                patch('app.server.os.path.exists', return_value=False):
            res = self.client.get('/api/network-info')

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['machine_ip'], '192.168.1.42')
        self.assertEqual(data['url_txt_machine'], 'http://192.168.1.42/')
        res.close()

    def test_api_network_info_with_localhost_host_header_in_docker(self):
        machine_socket = MagicMock()
        machine_socket.getsockname.return_value = ('172.19.0.2', 0)
        docker_socket = MagicMock()
        docker_socket.getsockname.return_value = ('172.19.0.2', 0)
        route_table = (
            "Iface Destination Gateway Flags RefCnt Use Metric Mask\n"
            "eth0 00000000 0101A8C0 0003 0 0 0 00000000\n"
        )

        with patch('app.server.socket.socket', side_effect=[machine_socket, docker_socket]), \
                patch('app.server.socket.gethostbyname', side_effect=OSError), \
                patch('app.server.os.path.exists', side_effect=lambda path: path == '/.dockerenv'), \
                patch('builtins.open', mock_open(read_data=route_table)):
            res = self.client.get('/api/network-info', headers={'Host': 'localhost'})

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['machine_ip'], '192.168.1.1')
        self.assertEqual(data['docker_ip'], '172.19.0.2')
        self.assertEqual(data['url_txt_machine'], 'http://192.168.1.1/')
        res.close()

    def test_no_remote_sources_and_local_assets_served(self):
        """UI pages must only reference local assets (no CDN/fonts), and those assets must be served."""
        import re
        pages = ['/', '/manage', '/docs']
        asset_paths = set()
        for url in pages:
            res = self.client.get(url)
            self.assertEqual(res.status_code, 200, url)
            html = res.data.decode("utf-8")
            res.close()
            refs = re.findall(r'(?:src|href)=["\']([^"\']+)["\']', html)
            refs += re.findall(r'@import\s+(?:url\()?["\']?([^"\')\s;]+)', html)
            for ref in refs:
                self.assertNotRegex(ref, r'^(?:https?:)?//', f"Remote source on {url}: {ref}")
                if ref.startswith('/static/'):
                    asset_paths.add(ref)
        self.assertIn('/static/css/style.css', asset_paths)
        self.assertIn('/static/vendor/swagger-ui/swagger-ui-bundle.js', asset_paths)
        for path in asset_paths:
            res = self.client.get(path)
            self.assertEqual(res.status_code, 200, path)
            res.close()

    def test_index2_json_listing_has_no_banner(self):
        """The web UI JSON listing must only contain real files, never the info banner."""
        res = self.client.get('/index2.php?type=ALL&web=1')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.mimetype, "application/json")
        self.assertFalse(any(item["name"].startswith("mpd [") for item in res.get_json()))

    def test_msx_pico_server_info_banner_injected(self):
        """Verify that server name and IP banner is injected at the top of the MSX listing."""
        res = self.client.get('/index2.php?type=ROM')
        self.assertEqual(res.status_code, 200)
        first_line = res.data.decode("utf-8").split("\n")[0]
        self.assertTrue(first_line.startswith("mpd ["))
        
        # Test downloading banner index 0 returns friendly info ROM
        res_dl = self.client.get('/index2.php?type=ROM&download=0')
        self.assertEqual(res_dl.status_code, 200)
        self.assertIn(b"name:server_info.rom", res_dl.data)
        res_dl.close()

    def test_msx_pico_com_support_and_nested_files_detection(self):
        """Verify that .com files placed directly in deep subdirectories under files/ are detected and served."""
        nested_dir = os.path.join(SERVE_DIRECTORY, "dev_builds", "project_x")
        os.makedirs(nested_dir, exist_ok=True)
        com_file = os.path.join(nested_dir, "testgame.com")
        
        # Write dummy binary content
        with open(com_file, "wb") as f:
            f.write(b"\xC9RET_TEST_COM") # Z80 RET instruction + payload
            
        try:
            # 1. Verify index listing for type=ROM
            res = self.client.get('/index2.php?type=ROM')
            self.assertEqual(res.status_code, 200)
            self.assertIn(b"testgame", res.data)
            
            # 2. Verify index listing for type=COM
            res_com = self.client.get('/index2.php?type=COM')
            self.assertEqual(res_com.status_code, 200)
            self.assertIn(b"testgame", res_com.data)

            # 3. Download the COM file via /index2.php?type=ROM&download=X
            # Parse line index
            lines = res.data.decode("utf-8").strip().split("\n")
            target_idx = None
            for idx, line in enumerate(lines):
                if "testgame" in line:
                    target_idx = idx
                    break
            self.assertIsNotNone(target_idx, "Created .com file was not found in listing!")

            dl_res = self.client.get(f'/index2.php?type=ROM&download={target_idx}')
            self.assertEqual(dl_res.status_code, 200)
            # Check header converts to .rom for MSX Pico loader compatibility
            self.assertIn(b"name:testgame.rom", dl_res.data)
            # Check padding to 4096 bytes
            header, content = dl_res.data.split(b"\n", 1)
            self.assertEqual(len(content), 4096)
            self.assertTrue(content.startswith(b"\xC9RET_TEST_COM"))
            dl_res.close()
        finally:
            if os.path.exists(com_file):
                os.remove(com_file)
            if os.path.exists(nested_dir):
                os.removedirs(nested_dir)

if __name__ == "__main__":
    unittest.main()
