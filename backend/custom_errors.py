class InsufficientBookDepth(Exception):
	def __init__(self, remaining_value):
		self.message = "Book depth is not sufficient to fill order."
		self.remaining_value = remaining_value
		super().__init__(self.message)