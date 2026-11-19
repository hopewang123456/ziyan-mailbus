package io.github.hopewang123456.mailbus.system;

import io.github.hopewang123456.mailbus.common.ApiException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

/** 运行时契约：与 Python 的 /api/openapi.json 保持同一份内容。 */
@RestController
public class OpenApiController {

    private final Path contract;

    public OpenApiController(
            @Value("${mailbus.contract-path:../shared/contracts/generated/openapi.json}")
            String contractPath) {
        this.contract = Path.of(contractPath);
    }

    @GetMapping(value = "/api/openapi.json", produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<byte[]> contract() throws IOException {
        if (!Files.isRegularFile(contract)) {
            throw ApiException.notFound("接口契约文件不存在");
        }
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(Files.readAllBytes(contract));
    }
}
