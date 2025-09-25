import re

# Command constants
CMD_ARCHIVE_ONLY = 'ao'
CMD_DOMAIN_OVERRIDE_PREFIX = '.'

def parse_commands_from_text(raw_text: str):
    """
    Parses special commands from a text string and returns the cleaned text
    and a dictionary of found commands.

    Commands are in the format [command].
    Example: "Tifa, (Cloud, Zack) [.st] [ao]"

    Returns:
        tuple[str, dict]: A tuple containing:
                          - The text string with commands removed.
                          - A dictionary of commands and their values.
                            e.g., {'domain_override': 'st', 'archive_only': True}
    """
    command_pattern = re.compile(r'\[(.*?)\]')
    commands = {}
    
    def command_replacer(match):
        command_str = match.group(1).strip()
        
        if command_str.startswith(CMD_DOMAIN_OVERRIDE_PREFIX):
            tld = command_str[len(CMD_DOMAIN_OVERRIDE_PREFIX):]
            if 'domain_override' not in commands: # Only take the first one
                commands['domain_override'] = tld
        elif command_str.lower() == CMD_ARCHIVE_ONLY:
            commands['archive_only'] = True
            
        return '' # Remove the command from the string

    text_without_commands = command_pattern.sub(command_replacer, raw_text).strip()
    
    return text_without_commands, commands