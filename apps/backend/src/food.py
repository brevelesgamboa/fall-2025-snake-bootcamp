import random
from typing import Tuple, Any


class Food:
    """
    Food class representing the collectible items in the Snake game.

    The food spawns randomly on the grid and respawns in a new location
    when eaten by the snake. It ensures it never spawns on the snake's body.
    """

    def __init__(self, game: Any) -> None:
        """Initialize food at a random position on the grid."""
        self.game = game
        self.position: Tuple[int, int] = (
            random.randint(0, game.grid_width - 1),
            random.randint(0, game.grid_height - 1),
        )
        self.eaten: bool = False
        # ensure initial spawn is not on the snake (or previous food)
        self.eaten = True
        self.spawn_food()


    def spawn_food(self) -> None:
        """
        Spawn new food in a random empty location.

        This method ensures the food doesn't appear on the snake's body
        or in the same location as the previous food.
        """
        if self.eaten:
            # Create a list of all positions that are NOT valid for food
            # (snake body + current food position)
            invalid_positions = self.game.snake.body + [self.position]

            # Generate all possible valid positions on the grid
            valid_positions = [
                (x, y)
                for x in range(self.game.grid_width)
                for y in range(self.game.grid_height)
                if (x, y) not in invalid_positions
            ]

            # If no valid positions exist, the game is over (snake fills the grid)
            if not valid_positions:
                self.game.game_over()
                return

            # Randomly choose from valid positions
            self.position = random.choice(valid_positions)
            self.eaten = False  # Reset the eaten flag

    def check_eaten(self) -> None:
        """
        Check if the snake's head is on the food position.

        If the food is eaten:
        1. Mark it as eaten
        2. Increase the game score
        3. Make the snake grow
        4. Spawn new food
        """
        # Check if the snake's head is at the same position as the food
        if self.position == self.game.snake.head:
            self.eaten = True  # Mark food as eaten
            self.game.score += 1  # Increase score
            self.game.snake.grow_snake()  # Make snake grow on next move
            self.spawn_food()  # Create new food elsewhere

    def to_dict(self) -> Tuple[int, int]:
        """
        Convert food to a format suitable for sending to the frontend.

        Returns:
            Tuple of (x, y) coordinates representing the food position
        """
        return self.position
