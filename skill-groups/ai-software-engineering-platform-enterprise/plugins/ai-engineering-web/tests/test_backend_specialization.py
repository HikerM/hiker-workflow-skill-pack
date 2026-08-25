from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "scripts"))

from backend_specialization import audit


def write(root: Path, relative: str, content: str) -> None:
    path = root / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(content, encoding="utf-8")


class BackendSpecializationTests(unittest.TestCase):
    def test_laravel_positive_evidence_covers_all_dimensions(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write(root, "composer.json", json.dumps({"require":{"php":"^8.3","laravel/framework":"^11.0"},"scripts":{"test":"php artisan test"}}))
            write(root, "composer.lock", json.dumps({"packages":[{"name":"laravel/framework","version":"v11.2.1"}]}))
            write(root, "routes/web.php", "Route::post('/orders', [OrderController::class, 'store']);")
            write(root, "app/Http/Controllers/OrderController.php", "class OrderController { function store(StoreOrderRequest $r, OrderService $s){ return $s->run(); } }")
            write(root, "app/Services/OrderService.php", "class OrderService { function run(){ return DB::transaction(fn()=>1); } }")
            write(root, "app/Http/Requests/StoreOrderRequest.php", "class StoreOrderRequest extends FormRequest { function rules(){ return []; } }")
            write(root, "app/Data/OrderData.php", "class OrderData {}")
            write(root, "app/Jobs/OrderJob.php", "class OrderJob implements ShouldQueue {}")
            write(root, "app/Policies/OrderPolicy.php", "class OrderPolicy { function create(){ return true; } }")
            write(root, "database/migrations/2026_01_create_orders.php", "$table->uuid('id')->primary(); $table->index('status');")
            write(root, "tests/Feature/OrderTest.php", "class OrderTest extends TestCase {}")
            write(root, "phpunit.xml", "<phpunit/>")
            data = audit(root, "laravel")
            self.assertEqual("PASS", data["result"], data)
            self.assertEqual("v11.2.1", data["identity"]["framework_resolved"])
            self.assertTrue(all(item["status"] == "PASS" for item in data["dimensions"].values()))
            self.assertEqual("paths-versions-status-hashes-only", data["storage_policy"])

    def test_laravel_negative_detects_unresolved_version_and_controller_leak(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write(root, "composer.json", json.dumps({"require":{"php":"^8.2","laravel/framework":"^10.0"}}))
            write(root, "routes/api.php", "Route::get('/x', [XController::class, 'show']);")
            write(root, "app/Http/Controllers/XController.php", "class XController { function show(){ return DB::table('x')->update([]); } }")
            write(root, "app/Services/XService.php", "class XService {}")
            write(root, "tests/Feature/XTest.php", "class XTest extends TestCase {}")
            write(root, "phpunit.xml", "<phpunit/>")
            data = audit(root, "laravel")
            self.assertEqual("FAIL", data["result"])
            self.assertEqual("GAP", data["dimensions"]["identity"]["status"])
            rules = {item["rule"] for item in data["dimensions"]["route_controller_service_boundary"]["findings"]}
            self.assertIn("controller-persistence-leak", rules)

    def test_node_typescript_positive_evidence_covers_build_contract_and_db(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write(root, "package.json", json.dumps({
                "engines":{"node":">=22"}, "packageManager":"pnpm@9",
                "dependencies":{"@nestjs/core":"11.0.0","@prisma/client":"6.0.0"},
                "devDependencies":{"typescript":"5.8.0"},
                "scripts":{"build":"tsc -p tsconfig.json","typecheck":"tsc --noEmit","test":"vitest run"},
            }))
            write(root, "pnpm-lock.yaml", "lockfileVersion: '9.0'\n")
            write(root, "tsconfig.json", json.dumps({"compilerOptions":{"strict":True}}))
            write(root, "src/orders/orders.module.ts", "export class OrdersModule {}")
            write(root, "src/orders/orders.controller.ts", "export class OrdersController { constructor(private service: OrdersService){} async list(){ return this.service.list(); } }")
            write(root, "src/orders/orders.service.ts", "export class OrdersService { async list(){ try { return []; } catch (error) { throw error; } } }")
            write(root, "src/common/http-error.filter.ts", "export class HttpErrorFilter extends ExceptionFilter {}")
            write(root, "openapi.yaml", "openapi: 3.1.0\n")
            write(root, "prisma/migrations/001/migration.sql", "CREATE TABLE orders(id uuid primary key);\n")
            write(root, "src/orders/orders.service.spec.ts", "describe('orders',()=>{});\n")
            data = audit(root, "node-ts")
            self.assertEqual("PASS", data["result"], data)
            self.assertEqual("NestJS", data["identity"]["framework"])
            self.assertTrue(all(item["status"] == "PASS" for item in data["dimensions"].values()))

    def test_node_typescript_negative_blocks_missing_lock_and_flags_controller_db(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write(root, "package.json", json.dumps({"dependencies":{"express":"5.1.0","prisma":"6.0.0"},"scripts":{"build":"tsc"}}))
            write(root, "tsconfig.json", "{}")
            write(root, "src/user.controller.ts", "export class UserController { async run(){ return prisma.user.findMany(); } }")
            write(root, "src/user.service.ts", "export class UserService {}")
            data = audit(root, "node-ts")
            self.assertEqual("BLOCKED", data["result"])
            self.assertIn("missing-package-lock", {item["rule"] for item in data["dimensions"]["identity_and_lock"]["findings"]})
            self.assertIn("controller-database-leak", {item["rule"] for item in data["dimensions"]["module_boundary"]["findings"]})

    def test_default_audit_does_not_write_state(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); write(root, "package.json", "{}")
            audit(root, "node-ts")
            self.assertFalse((root / ".ai").exists())


if __name__ == "__main__":
    unittest.main()
