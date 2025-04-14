start:
	sudo docker compose up --build

stop:
	sudo docker compose down --timeout 100

build-images:
	cd server && docker build -t server:v1 .

up: build-images
	sudo docker compose up --build -d

clean:
	sudo docker compose down --timeout 100 --volumes --remove-orphans
	sudo docker system prune -f
