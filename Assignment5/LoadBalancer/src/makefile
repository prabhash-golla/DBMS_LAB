start:
	sudo docker-compose up --build

stop:
	sudo docker-compose down --timeout 100

build-images:
	cd server && docker build -t server:v1 .

up: build-images
	docker-compose up --build -d

test:
	cd client && python3 client.py 5000 TEST 

test_ic:
	cd client && python3 client.py 

clean:
	docker-compose down --timeout 100 --volumes --remove-orphans
	docker system prune -f
