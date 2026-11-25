package io.github.hopewang123456.mailbus.layout;

import io.github.hopewang123456.mailbus.collab.ScreenService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class LayoutController {

    private final LayoutService service;
    private final ScreenService screens;

    public LayoutController(LayoutService service, ScreenService screens) {
        this.service = service;
        this.screens = screens;
    }

    @GetMapping("/layout")
    public LayoutDtos.OfficeSiteOut layout() {
        return service.get();
    }

    /** 按屏幕已发布配置过滤团队；公开投影不含 team。 */
    @GetMapping("/public/layout")
    public LayoutDtos.PublicOfficeSiteOut publicLayout(
            @RequestParam(name = "screen_id", required = false) String screenId) {
        String teamId = screenId == null || screenId.isBlank()
                ? null : screens.publishedTeamId(screenId);
        return service.getPublic(teamId);
    }
}
