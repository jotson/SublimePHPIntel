# SublimePHPIntel

PHP code scanner and analyzer for code intelligence within PHP projects.

## Setup

1. Create or open a project with PHP files
2. Run the PHPIntel: Scan Project command from the command palette

After the initial scan, PHP files will be automatically re-scanned whenever you save them.

## Go to declaration

To open a class declaration, place your cursor on the class name and press `Ctrl+f5` or `Cmd+f5`

## Known issues

I'm working on these issues:

- Variable assignment is not detected (for example: $var = <code> where code returns an object.
- Like most code intelligence features, it doesn't understand factory methods like Class::model(). I'm planning to add regex patterns which you can customize per project to detect those and return the correct class.
- Files are not removed from the index when they are deleted. For now, you'll need to rescan to remove them.
- Files added to the project from outside of the editor are not added to the index. For now, you'll either need to open the file and save it or rescan the project.
- I'm not completely happy with the way it deals with cases where the same class is declared more than once. Need to do some research to see how others deal with that.