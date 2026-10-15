package io.github.hopewang123456.mailbus.ports;

import io.github.hopewang123456.mailbus.domain.message.MsgRecord;

import java.nio.file.Path;

/**
 * Archive port — moves a settled message file to the archive tree
 * (archive/&lt;agent&gt;/&lt;yyyy-MM-dd&gt;/&lt;id&gt;.json) and returns its new path.
 */
public interface MessageArchiver {

    Path archive(MsgRecord record);
}
